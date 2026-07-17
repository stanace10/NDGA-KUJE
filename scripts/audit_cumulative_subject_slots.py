"""Audit Third-Term anchored annual cumulative subject slots.

Writes a CSV showing which historical rows are used for every current Third
Term subject, including inferred subject switches and genuine absent terms.
"""

from __future__ import annotations

import csv
from pathlib import Path

from apps.academics.models import AcademicClass, AcademicSession, StudentClassEnrollment, Term
from apps.academics.subject_policy import NON_RESULT_SUBJECT_CODES, exclude_non_result_subjects
from apps.results.annual_subjects import build_annual_subject_slots, generic_annual_subject_label
from apps.results.models import ResultSheetStatus, StudentSubjectScore


SESSION_NAME = "2025/2026"
CLASS_CODES = ("JS1", "JS2", "JS3", "SS1", "SS2", "SS3")
TERM_ORDER = ("FIRST", "SECOND", "THIRD")
OUTPUT_PATH = Path("/app/SCHOOL FOLDER/cumulative-subject-slot-audit-20260715.csv")
DISPLAY_OUTPUT_PATH = Path("/app/SCHOOL FOLDER/cumulative-display-audit-20260715.csv")


def _student_name(student):
    parts = [student.last_name, student.first_name]
    profile = getattr(student, "student_profile", None)
    middle = getattr(profile, "middle_name", "") if profile else ""
    if middle:
        parts.append(middle)
    return " ".join(part for part in parts if part).strip() or student.username


def _admission(student):
    profile = getattr(student, "student_profile", None)
    return getattr(profile, "student_number", "") or student.username


def _score_total(row):
    return getattr(row, "grand_total", None)


def _average(rows):
    if not rows:
        return None
    return sum((_score_total(row) for row in rows), start=0) / len(rows)


def _display_score(value):
    if value is None:
        return ""
    try:
        return f"{value:.2f}"
    except Exception:
        return str(value)


def run():
    session = AcademicSession.objects.get(name=SESSION_NAME)
    terms = {term.name: term for term in Term.objects.filter(session=session, name__in=TERM_ORDER)}
    output_rows = []
    display_rows = []

    for class_code in CLASS_CODES:
        academic_class = AcademicClass.objects.filter(code=class_code).first()
        if academic_class is None:
            continue
        instructional_class = academic_class.instructional_class
        cohort_class_ids = academic_class.cohort_class_ids()
        enrollments = list(
            StudentClassEnrollment.objects.filter(
                academic_class_id__in=cohort_class_ids,
                session=session,
                is_active=True,
            )
            .select_related("student", "student__student_profile", "academic_class")
            .order_by("student__student_profile__student_number", "student__last_name", "student__first_name")
        )
        student_ids = [enrollment.student_id for enrollment in enrollments]
        score_qs = StudentSubjectScore.objects.filter(
            student_id__in=student_ids,
            result_sheet__session=session,
            result_sheet__term__name__in=TERM_ORDER,
            result_sheet__academic_class=instructional_class,
        ).exclude(
            result_sheet__status__in=[
                ResultSheetStatus.DRAFT,
                ResultSheetStatus.REJECTED_BY_DEAN,
                ResultSheetStatus.REJECTED_BY_VP,
            ]
        ).select_related("student", "student__student_profile", "result_sheet__term", "result_sheet__subject")
        score_qs = exclude_non_result_subjects(score_qs, field_name="result_sheet__subject")

        by_student = {}
        for score in score_qs:
            by_student.setdefault(score.student_id, {}).setdefault(score.result_sheet.term.name, []).append(
                (score.result_sheet.subject.name, score)
            )

        slots_by_student = {}
        diagnostics_by_student = {}
        display_sources_by_student = {}
        target_merge_sources_by_student = {}
        class_term_subject_labels = {term: set() for term in TERM_ORDER}
        for enrollment in enrollments:
            student = enrollment.student
            term_rows = by_student.get(student.id, {})
            slots, diagnostics = build_annual_subject_slots(term_rows, student=student)
            slots_by_student[student.id] = slots
            diagnostics_by_student[student.id] = diagnostics
            display_sources = {}
            target_merge_sources = {}
            for subject, term_map in slots.items():
                for term_name in TERM_ORDER:
                    if term_map.get(term_name):
                        class_term_subject_labels.setdefault(term_name, set()).add(subject)
                    for score in term_map.get(term_name, []):
                        actual_label = generic_annual_subject_label(score.result_sheet.subject.name, row=score)
                        if actual_label == subject:
                            continue
                        display_sources.setdefault(
                            actual_label,
                            {"merged_to": subject, "terms": {}},
                        )["terms"].setdefault(term_name, []).append(score)
                        target_merge_sources.setdefault(subject, {})[term_name] = actual_label
            display_sources_by_student[student.id] = display_sources
            target_merge_sources_by_student[student.id] = target_merge_sources

        for enrollment in enrollments:
            student = enrollment.student
            term_rows = by_student.get(student.id, {})
            if not term_rows.get("THIRD"):
                output_rows.append(
                    {
                        "class": class_code,
                        "admission": _admission(student),
                        "student": _student_name(student),
                        "annual_subject": "",
                        "status": "NO_THIRD_TERM_RESULT_EXCLUDED_FROM_CUMULATIVE",
                        "first_subjects_used": "",
                        "first_score": "",
                        "second_subjects_used": "",
                        "second_score": "",
                        "third_subjects_used": "",
                        "third_score": "",
                        "term_count": 0,
                        "annual_average": "",
                        "diagnostic": "Student has no published Third Term result rows in current class.",
                    }
                )
                continue

            slots = slots_by_student.get(student.id, {})
            diagnostics = diagnostics_by_student.get(student.id, [])
            display_subjects = sorted(set(slots) | set(display_sources_by_student.get(student.id, {})))
            for subject in display_subjects:
                source_info = display_sources_by_student.get(student.id, {}).get(subject)
                is_display_only = source_info is not None and subject not in slots
                merged_to = source_info["merged_to"] if source_info else ""
                row = {
                    "class": class_code,
                    "admission": _admission(student),
                    "student": _student_name(student),
                    "display_subject": subject,
                    "display_only": "YES" if is_display_only else "NO",
                    "merged_to": merged_to,
                    "official_subject": "" if is_display_only else subject,
                    "first": "",
                    "second": "",
                    "third": "",
                    "official_term_count": "",
                    "official_total": "",
                    "official_average": "",
                    "note": "",
                }
                official_values = []
                official_total = 0
                for term_name, column in zip(TERM_ORDER, ("first", "second", "third")):
                    if is_display_only:
                        rows = source_info["terms"].get(term_name, [])
                        value = _average(rows)
                        if value is not None:
                            row[column] = _display_score(value)
                        elif slots.get(merged_to, {}).get(term_name):
                            row[column] = f"Merged with {merged_to}"
                        elif not term_rows.get(term_name):
                            row[column] = "Not a student"
                        elif subject not in class_term_subject_labels.get(term_name, set()):
                            row[column] = "Not offered"
                        else:
                            row[column] = "Did not offer"
                    else:
                        rows = slots.get(subject, {}).get(term_name, [])
                        value = _average(rows)
                        if value is not None:
                            actual = target_merge_sources_by_student.get(student.id, {}).get(subject, {}).get(term_name)
                            row[column] = f"Merged from {actual}" if actual else _display_score(value)
                            official_values.append(value)
                            official_total += value
                        elif not term_rows.get(term_name):
                            row[column] = "Not a student"
                        elif subject not in class_term_subject_labels.get(term_name, set()):
                            row[column] = "Not offered"
                        else:
                            row[column] = "Did not offer"
                if is_display_only:
                    row["note"] = f"Historical display row only; official cumulative is in {merged_to}."
                else:
                    row["official_term_count"] = len(official_values)
                    row["official_total"] = _display_score(official_total)
                    row["official_average"] = _display_score(official_total / len(official_values)) if official_values else ""
                display_rows.append(row)

            for subject in sorted(slots):
                term_map = slots[subject]
                if not term_map.get("THIRD"):
                    continue
                used = {}
                values = []
                for term_name in TERM_ORDER:
                    rows = term_map.get(term_name, [])
                    used[term_name] = rows
                    if rows:
                        avg = sum((_score_total(row) for row in rows), start=0) / len(rows)
                        values.append(avg)
                annual_average = sum(values, start=0) / len(values) if values else ""
                not_applicable = []
                for term in TERM_ORDER:
                    if used.get(term):
                        continue
                    not_applicable.append(term.title())
                status = "OK"
                if not_applicable:
                    status = f"DIVIDE_BY_{len(values)}_NOT_APPLICABLE_{'/'.join(not_applicable)}"
                output_rows.append(
                    {
                        "class": class_code,
                        "admission": _admission(student),
                        "student": _student_name(student),
                        "annual_subject": subject,
                        "status": status,
                        "first_subjects_used": " + ".join(row.result_sheet.subject.name for row in used.get("FIRST", [])),
                        "first_score": " + ".join(str(_score_total(row)) for row in used.get("FIRST", [])),
                        "second_subjects_used": " + ".join(row.result_sheet.subject.name for row in used.get("SECOND", [])),
                        "second_score": " + ".join(str(_score_total(row)) for row in used.get("SECOND", [])),
                        "third_subjects_used": " + ".join(row.result_sheet.subject.name for row in used.get("THIRD", [])),
                        "third_score": " + ".join(str(_score_total(row)) for row in used.get("THIRD", [])),
                        "term_count": len(values),
                        "annual_average": annual_average,
                        "diagnostic": "",
                    }
                )

            for diagnostic in diagnostics:
                output_rows.append(
                    {
                        "class": class_code,
                        "admission": _admission(student),
                        "student": _student_name(student),
                        "annual_subject": diagnostic.get("subject", ""),
                        "status": "DIAGNOSTIC",
                        "first_subjects_used": "",
                        "first_score": "",
                        "second_subjects_used": "",
                        "second_score": "",
                        "third_subjects_used": "",
                        "third_score": "",
                        "term_count": "",
                        "annual_average": "",
                        "diagnostic": f"{diagnostic.get('term', '')}: {diagnostic.get('reason', '')}; total={diagnostic.get('total') or diagnostic.get('new_total') or ''}",
                    }
                )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0].keys()) if output_rows else [])
        writer.writeheader()
        writer.writerows(output_rows)
    with DISPLAY_OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(display_rows[0].keys()) if display_rows else [])
        writer.writeheader()
        writer.writerows(display_rows)
    print({
        "written": str(OUTPUT_PATH),
        "rows": len(output_rows),
        "display_written": str(DISPLAY_OUTPUT_PATH),
        "display_rows": len(display_rows),
    })


if __name__ == "__main__":
    run()
