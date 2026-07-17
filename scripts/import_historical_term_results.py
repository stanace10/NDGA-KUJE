from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import django

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.accounts.constants import ROLE_STUDENT
from apps.accounts.models import Role, StudentProfile
from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    ClassSubject,
    Subject,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
    TeacherSubjectAssignment,
    Term,
    TermName,
)
from apps.results.models import (
    ClassCompilationStatus,
    ClassResultCompilation,
    ClassResultStudentRecord,
    ResultSheet,
    StudentSubjectScore,
)


User = get_user_model()

TERM_DIR_TO_NAME = {
    "FIRST TERM": TermName.FIRST,
    "1ST TERM": TermName.FIRST,
    "SECOND TERM": TermName.SECOND,
    "2ND TERM": TermName.SECOND,
}

NON_RESULT_SUBJECT_CODES = {"CHN", "GER", "SGL"}


def normalize(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.replace("–", "-").replace("—", "-").replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


SUBJECT_ALIASES = {
    "english studies": "ENG",
    "english language": "ENG",
    "english": "ENG",
    "mathematics": "MTH",
    "maths": "MTH",
    "further mathematics": "FTM",
    "further maths": "FTM",
    "basic science": "BSC",
    "bst basic science": "BSC",
    "basic technology": "BTE",
    "bst basic technology": "BTE",
    "bst computer studies": "CPS",
    "bst computer science": "CSC",
    "physical and health education": "PHE",
    "bst physical health education": "PHE",
    "bst physical and health education": "PHE",
    "business studies": "BST",
    "cca art": "CCA",
    "cultural and creative art": "CCA",
    "cultural creative art": "CCA",
    "cca": "CCA",
    "cca music": "MUS",
    "music": "MUS",
    "history": "HIS",
    "civic education": "CVC",
    "rnv civic education": "CVC",
    "french": "FRE",
    "igbo language": "IGB",
    "igbo": "IGB",
    "hausa": "HAU",
    "hausa language": "HAU",
    "christian religious studies": "CRS",
    "rnv christian religious studies": "CRS",
    "crs": "CRS",
    "digital technologies": "DIT",
    "digital technology": "DIT",
    "computer studies": "CPS",
    "computer science": "CSC",
    "data processing": "DAP",
    "livestock farming": "LIV",
    "livestock": "LIV",
    "social citizenship studies": "SCS",
    "social and citizenship studies": "SCS",
    "social studies": "SST",
    "rnv social studies": "SST",
    "fashion garment making": "FAS",
    "fashion": "FAS",
    "garment making": "FAS",
    "visual art": "VAT",
    "biology": "BIO",
    "chemistry": "CHM",
    "physics": "PHY",
    "geography": "GEO",
    "agricultural science": "AGR",
    "agric science": "AGR",
    "fishery": "FSH",
    "technical drawing": "TDR",
    "government": "GOV",
    "commerce": "COM",
    "economics": "ECO",
    "accounting": "ACC",
    "financial accounting": "ACC",
    "literature": "LIT",
    "literature in english": "LIT",
    "english literature": "LIT",
    "food and nutrition": "FDN",
    "foods and nutrition": "FDN",
    "home economics": "HEC",
    "pvs home economics": "HEC",
    "home management": "HMG",
    "catering craft": "CTC",
    "yoruba": "YOR",
    "yoruba language": "YOR",
}


NUMERIC_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
ADMISSION_RE = re.compile(r"NDGAK/\d{2}/(\d+)", re.IGNORECASE)
STOP_RE = re.compile(r"^(analysis|psycomotor domain|psychomotor domain|cognitive domain rating)$", re.IGNORECASE)


@dataclass
class ParsedSubjectRow:
    raw_subject: str
    ca1: Decimal
    ca2: Decimal
    ca3: Decimal
    ca4: Decimal
    exam: Decimal
    total: Decimal
    grade: str
    remark: str
    position: str
    lowest: Decimal | None
    highest: Decimal | None
    average: Decimal | None


@dataclass
class ParsedPdf:
    path: Path
    admission_suffix: str
    admission_number: str
    student_name: str
    rows: list[ParsedSubjectRow]
    issues: list[str]


def to_decimal(value: str) -> Decimal:
    try:
        return Decimal(str(value).replace(",", "").strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, AttributeError):
        raise ValueError(f"Invalid numeric value: {value!r}")


def is_numeric(value: str) -> bool:
    return bool(NUMERIC_RE.match((value or "").strip()))


def extract_text(path: Path) -> str:
    completed = subprocess.run(
        ["pdftotext", str(path), "-"],
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout


def find_header_start(lines: list[str]) -> int:
    try:
        report_idx = next(i for i, line in enumerate(lines) if normalize(line) == "termly evaluation report")
    except StopIteration:
        report_idx = 0
    for i in range(report_idx, min(len(lines), report_idx + 80)):
        normalized = normalize(lines[i])
        if normalized == "average" or normalized.endswith("highest score average"):
            return i + 1
    raise ValueError("Could not find result table header ending with Average")


def parse_pdf(path: Path) -> ParsedPdf:
    text = extract_text(path)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    admission_match = ADMISSION_RE.search(text)
    admission_number = admission_match.group(0).upper() if admission_match else ""
    admission_suffix = admission_match.group(1) if admission_match else path.stem
    student_name = ""
    if "STUDENTS NAME:" in text:
        try:
            name_idx = lines.index("STUDENTS NAME:")
            for candidate in lines[name_idx + 1 : name_idx + 8]:
                if candidate not in {"CLASS:", "NO. IN CLASS:"} and not candidate.startswith("office@"):
                    student_name = candidate
                    break
        except ValueError:
            pass

    rows: list[ParsedSubjectRow] = []
    issues: list[str] = []
    i = find_header_start(lines)
    while i < len(lines):
        if STOP_RE.match(lines[i]):
            break
        if normalize(lines[i]) in {"subject", "score", "color", "grade", "score range", "remark"}:
            i += 1
            continue
        if is_numeric(lines[i]):
            issues.append(f"Unexpected numeric line before subject at line {i + 1}: {lines[i]}")
            i += 1
            continue

        subject_parts = []
        while i < len(lines) and not is_numeric(lines[i]):
            if STOP_RE.match(lines[i]):
                break
            subject_parts.append(lines[i])
            i += 1
        if not subject_parts or i >= len(lines) or STOP_RE.match(lines[i]):
            break
        raw_subject = " ".join(subject_parts).strip()

        try:
            number_tokens = []
            while i < len(lines) and is_numeric(lines[i]):
                number_tokens.append(to_decimal(lines[i]))
                i += 1
            if len(number_tokens) >= 6:
                ca1, ca2, ca3, ca4, exam, total = number_tokens[:6]
            elif len(number_tokens) == 5:
                ca1, ca2, ca3, fourth, fifth = number_tokens
                if abs((ca1 + ca2 + ca3 + fourth) - fifth) <= Decimal("0.05"):
                    ca4 = fourth
                    exam = Decimal("0.00")
                    total = fifth
                    issues.append(f"{raw_subject}: exam score missing in PDF row; imported exam as 0 and preserved total {total}")
                else:
                    ca4 = Decimal("0.00")
                    exam = fourth
                    total = fifth
                    issues.append(f"{raw_subject}: project/assignment score missing in PDF row; imported project as 0 and preserved total {total}")
            elif len(number_tokens) == 4:
                ca1, ca2, ca3, total = number_tokens
                ca4 = Decimal("0.00")
                exam = Decimal("0.00")
                issues.append(f"{raw_subject}: project and exam scores missing in PDF row; preserved printed total {total}")
            else:
                raise ValueError(f"Expected at least 4 numeric score values, found {len(number_tokens)}")

            grade = lines[i].strip()
            remark = lines[i + 1].strip()
            position = lines[i + 2].strip()
            lowest = to_decimal(lines[i + 3]) if is_numeric(lines[i + 3]) else None
            highest = to_decimal(lines[i + 4]) if is_numeric(lines[i + 4]) else None
            average = to_decimal(lines[i + 5]) if is_numeric(lines[i + 5]) else None
            i += 6
        except (IndexError, ValueError) as exc:
            issues.append(f"{raw_subject}: could not parse full score row ({exc})")
            break

        computed = (ca1 + ca2 + ca3 + ca4 + exam).quantize(Decimal("0.01"))
        if abs(computed - total) > Decimal("0.05"):
            issues.append(f"{raw_subject}: component sum {computed} differs from printed total {total}")
        rows.append(
            ParsedSubjectRow(
                raw_subject=raw_subject,
                ca1=ca1,
                ca2=ca2,
                ca3=ca3,
                ca4=ca4,
                exam=exam,
                total=total,
                grade=grade,
                remark=remark,
                position=position,
                lowest=lowest,
                highest=highest,
                average=average,
            )
        )

    if not rows:
        issues.append("No subject score rows parsed")
    return ParsedPdf(
        path=path,
        admission_suffix=admission_suffix,
        admission_number=admission_number,
        student_name=student_name,
        rows=rows,
        issues=issues,
    )


def build_subject_map():
    by_code = {subject.code.upper(): subject for subject in Subject.objects.all()}
    by_name = {normalize(subject.name): subject for subject in Subject.objects.all()}

    def resolve(raw_subject: str):
        key = normalize(raw_subject)
        code = SUBJECT_ALIASES.get(key)
        if code:
            return by_code.get(code)
        return by_name.get(key)

    return resolve


def student_by_suffix():
    students = {}
    for user in User.objects.select_related("student_profile").filter(student_profile__isnull=False):
        number = (user.student_profile.student_number or "").strip()
        match = re.search(r"(\d+)$", number)
        if match:
            students.setdefault(match.group(1), []).append(user)
    return students


def pick_student(index: dict[str, list], suffix: str):
    matches = index.get(str(int(suffix)) if suffix.isdigit() else suffix, [])
    if len(matches) == 1:
        return matches[0], ""
    if not matches:
        return None, "student not found"
    return None, f"multiple students matched suffix {suffix}: {[m.username for m in matches]}"


def split_student_name(full_name: str):
    parts = [part.strip() for part in (full_name or "").title().split() if part.strip()]
    if not parts:
        return "Historical", "Student", ""
    if len(parts) == 1:
        return parts[0], "Student", ""
    first_name = parts[0]
    last_name = parts[-1]
    middle_name = " ".join(parts[1:-1])
    return first_name, last_name, middle_name


def unique_username_for_admission(admission_number: str):
    base = (admission_number or "").lower().replace("/", "-").replace(" ", "-")
    base = re.sub(r"[^a-z0-9-]+", "-", base).strip("-") or "historical-student"
    candidate = base
    counter = 2
    while User.objects.filter(username=candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def ensure_historical_student(*, parsed: ParsedPdf, academic_class, session, counters):
    role_student, _ = Role.objects.get_or_create(
        code=ROLE_STUDENT,
        defaults={"name": "Student", "is_system": True},
    )
    admission_number = parsed.admission_number or f"NDGAK/00/{parsed.admission_suffix}"
    first_name, last_name, middle_name = split_student_name(parsed.student_name)
    user = User.objects.create(
        username=unique_username_for_admission(admission_number),
        first_name=first_name,
        last_name=last_name,
        primary_role=role_student,
        is_active=False,
        must_change_password=True,
    )
    user.set_unusable_password()
    user.save(update_fields=["password"])
    StudentProfile.objects.create(
        user=user,
        student_number=admission_number,
        middle_name=middle_name,
        lifecycle_state=StudentProfile.LifecycleState.TRANSFERRED,
        lifecycle_note="Created from imported 2025/2026 historical result PDF.",
    )
    if academic_class is not None:
        StudentClassEnrollment.objects.update_or_create(
            student=user,
            session=session,
            defaults={"academic_class": academic_class, "is_active": False},
        )
    counters["students_created"] += 1
    return user


def upsert_historical_score(*, sheet, student, row: ParsedSubjectRow, actor):
    total_ca = (row.ca1 + row.ca2 + row.ca3 + row.ca4).quantize(Decimal("0.01"))
    objective = min(row.exam, Decimal("20.00")).quantize(Decimal("0.01"))
    theory = max(row.exam - objective, Decimal("0.00")).quantize(Decimal("0.01"))
    score, created = StudentSubjectScore.objects.get_or_create(
        result_sheet=sheet,
        student=student,
    )
    breakdown = {
        "historical_import": "2025-2026 official PDF",
        "source_pdf": str(row.raw_subject),
        "old_exam_total_over_60": str(row.exam),
        "old_result_total": str(row.total),
        "printed_position": row.position,
    }
    StudentSubjectScore.objects.filter(pk=score.pk).update(
        ca1=row.ca1,
        ca2=row.ca2,
        ca3=row.ca3,
        ca4=row.ca4,
        class_participation=Decimal("0.00"),
        objective=objective,
        theory=theory,
        total_ca=total_ca,
        total_exam=row.exam,
        grand_total=row.total,
        grade=row.grade[:2],
        has_override=True,
        override_reason="Historical official PDF import; first/second-term exam used the old 60-mark exam structure.",
        override_by=actor,
        override_at=timezone.now(),
        cbt_locked_fields=[],
        cbt_component_breakdown=breakdown,
    )
    return created


def sync_historical_teacher_assignments(*, session, terms):
    third_term = Term.objects.filter(session=session, name=TermName.THIRD).first()
    created = 0
    unresolved = 0
    for sheet in ResultSheet.objects.select_related("academic_class", "subject", "term").filter(
        session=session,
        term__in=list(terms.values()),
    ):
        if TeacherSubjectAssignment.objects.filter(
            academic_class=sheet.academic_class,
            subject=sheet.subject,
            session=session,
            term=sheet.term,
            is_active=True,
        ).exists():
            continue
        source = None
        if sheet.term.name == TermName.FIRST:
            source = TeacherSubjectAssignment.objects.filter(
                academic_class=sheet.academic_class,
                subject=sheet.subject,
                session=session,
                term=terms[TermName.SECOND],
                is_active=True,
            ).first()
        if source is None and third_term is not None:
            source = TeacherSubjectAssignment.objects.filter(
                academic_class=sheet.academic_class,
                subject=sheet.subject,
                session=session,
                term=third_term,
                is_active=True,
            ).first()
        if source is None:
            source = TeacherSubjectAssignment.objects.filter(
                subject=sheet.subject,
                session=session,
                is_active=True,
            ).order_by("-term__name").first()
        if source is None:
            unresolved += 1
            continue
        TeacherSubjectAssignment.objects.create(
            teacher=source.teacher,
            subject=sheet.subject,
            academic_class=sheet.academic_class,
            session=session,
            term=sheet.term,
            is_active=True,
        )
        created += 1
    return created, unresolved


def import_root(root: Path, *, dry_run: bool, report_dir: Path):
    session = AcademicSession.objects.get(name="2025/2026")
    first_term, _ = Term.objects.get_or_create(session=session, name=TermName.FIRST)
    second_term, _ = Term.objects.get_or_create(session=session, name=TermName.SECOND)
    terms = {TermName.FIRST: first_term, TermName.SECOND: second_term}
    resolve_subject = build_subject_map()
    students = student_by_suffix()
    actor = User.objects.filter(is_superuser=True).first() or User.objects.filter(is_staff=True).first()

    rows_for_report = []
    counters = {
        "files": 0,
        "parsed_subject_rows": 0,
        "scores_created": 0,
        "scores_updated": 0,
        "records_created": 0,
        "records_updated": 0,
        "students_created": 0,
        "teacher_assignments_created": 0,
        "teacher_assignments_unresolved": 0,
        "skipped_subject_rows": 0,
        "files_with_issues": 0,
    }

    for pdf_path in sorted(root.rglob("*.pdf")):
        relative = pdf_path.relative_to(root)
        parts = relative.parts
        if len(parts) < 3:
            continue
        class_code = parts[0].upper()
        term_key = TERM_DIR_TO_NAME.get(parts[1].upper())
        if not term_key:
            continue
        counters["files"] += 1
        try:
            parsed = parse_pdf(pdf_path)
        except Exception as exc:
            counters["files_with_issues"] += 1
            rows_for_report.append(
                {
                    "file": str(relative),
                    "class": class_code,
                    "term": term_key,
                    "admission": pdf_path.stem,
                    "student_name_pdf": "",
                    "student_username": "",
                    "raw_subject": "",
                    "mapped_subject": "",
                    "ca1": "",
                    "ca2": "",
                    "ca3": "",
                    "assignment_project": "",
                    "exam_old_60": "",
                    "total": "",
                    "grade": "",
                    "action": "ISSUE",
                    "issue": f"PDF parse failed: {exc}",
                }
            )
            continue
        academic_class = AcademicClass.objects.filter(code__iexact=class_code).first()
        term = terms[term_key]
        student, student_issue = pick_student(students, parsed.admission_suffix)
        if student is None and academic_class is not None and student_issue == "student not found" and not dry_run:
            student = ensure_historical_student(
                parsed=parsed,
                academic_class=academic_class,
                session=session,
                counters=counters,
            )
            students.setdefault(parsed.admission_suffix, []).append(student)
            student_issue = ""

        file_has_issue = bool(parsed.issues or not academic_class or student_issue)
        if not academic_class:
            parsed.issues.append(f"class not found: {class_code}")
        if student_issue:
            parsed.issues.append(student_issue)

        compilation = None
        if academic_class and student and not dry_run:
            compilation, _ = ClassResultCompilation.objects.get_or_create(
                academic_class=academic_class,
                session=session,
                term=term,
                defaults={
                    "status": ClassCompilationStatus.PUBLISHED,
                    "published_at": timezone.now(),
                    "principal_override_actor": actor,
                    "decision_comment": "Historical first/second term official PDF import.",
                },
            )
            changed = False
            if compilation.status != ClassCompilationStatus.PUBLISHED:
                compilation.status = ClassCompilationStatus.PUBLISHED
                compilation.published_at = compilation.published_at or timezone.now()
                changed = True
            if changed:
                compilation.save(update_fields=["status", "published_at", "updated_at"])
            record, created_record = ClassResultStudentRecord.objects.update_or_create(
                compilation=compilation,
                student=student,
                defaults={
                    "attendance_percentage": Decimal("100.00"),
                    "behavior_rating": 3,
                    "management_status": "PENDING",
                },
            )
            counters["records_created" if created_record else "records_updated"] += 1

        for subject_row in parsed.rows:
            counters["parsed_subject_rows"] += 1
            subject = resolve_subject(subject_row.raw_subject)
            issue = ""
            action = "DRY-RUN" if dry_run else "SKIPPED"
            if subject is None:
                issue = f"subject not mapped: {subject_row.raw_subject}"
                counters["skipped_subject_rows"] += 1
                file_has_issue = True
            elif subject.code.upper() in NON_RESULT_SUBJECT_CODES:
                issue = "non-result subject skipped"
                counters["skipped_subject_rows"] += 1
            elif not (academic_class and student):
                issue = "class/student missing; score skipped"
                counters["skipped_subject_rows"] += 1
                file_has_issue = True
            elif dry_run:
                action = "WOULD_IMPORT"
            else:
                ClassSubject.objects.get_or_create(
                    academic_class=academic_class,
                    subject=subject,
                    defaults={"is_active": True},
                )
                sheet, _ = ResultSheet.objects.get_or_create(
                    academic_class=academic_class,
                    subject=subject,
                    session=session,
                    term=term,
                    defaults={"created_by": actor},
                )
                created_score = upsert_historical_score(
                    sheet=sheet,
                    student=student,
                    row=subject_row,
                    actor=actor,
                )
                counters["scores_created" if created_score else "scores_updated"] += 1
                action = "CREATED" if created_score else "UPDATED"

            rows_for_report.append(
                {
                    "file": str(relative),
                    "class": class_code,
                    "term": term_key,
                    "admission": parsed.admission_number or parsed.admission_suffix,
                    "student_name_pdf": parsed.student_name,
                    "student_username": getattr(student, "username", ""),
                    "raw_subject": subject_row.raw_subject,
                    "mapped_subject": getattr(subject, "name", ""),
                    "ca1": subject_row.ca1,
                    "ca2": subject_row.ca2,
                    "ca3": subject_row.ca3,
                    "assignment_project": subject_row.ca4,
                    "exam_old_60": subject_row.exam,
                    "total": subject_row.total,
                    "grade": subject_row.grade,
                    "action": action,
                    "issue": issue,
                }
            )

        for issue in parsed.issues:
            rows_for_report.append(
                {
                    "file": str(relative),
                    "class": class_code,
                    "term": term_key,
                    "admission": parsed.admission_number or parsed.admission_suffix,
                    "student_name_pdf": parsed.student_name,
                    "student_username": getattr(student, "username", ""),
                    "raw_subject": "",
                    "mapped_subject": "",
                    "ca1": "",
                    "ca2": "",
                    "ca3": "",
                    "assignment_project": "",
                    "exam_old_60": "",
                    "total": "",
                    "grade": "",
                    "action": "ISSUE",
                    "issue": issue,
                }
            )
        if file_has_issue:
            counters["files_with_issues"] += 1

    if not dry_run:
        created_assignments, unresolved_assignments = sync_historical_teacher_assignments(
            session=session,
            terms=terms,
        )
        counters["teacher_assignments_created"] = created_assignments
        counters["teacher_assignments_unresolved"] = unresolved_assignments

    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = report_dir / f"historical-term-import-report-{stamp}.csv"
    with report_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "file",
                "class",
                "term",
                "admission",
                "student_name_pdf",
                "student_username",
                "raw_subject",
                "mapped_subject",
                "ca1",
                "ca2",
                "ca3",
                "assignment_project",
                "exam_old_60",
                "total",
                "grade",
                "action",
                "issue",
            ],
        )
        writer.writeheader()
        writer.writerows(rows_for_report)
    return counters, report_path


def main():
    parser = argparse.ArgumentParser(description="Import 2025/2026 first and second term result PDFs.")
    parser.add_argument("--root", required=True, help="Folder containing class/term PDF subfolders.")
    parser.add_argument("--report-dir", default="/tmp", help="Folder for CSV import report.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(args.root)
    report_dir = Path(args.report_dir)
    if args.dry_run:
        counters, report_path = import_root(root, dry_run=True, report_dir=report_dir)
    else:
        with transaction.atomic():
            counters, report_path = import_root(root, dry_run=False, report_dir=report_dir)
    print("Historical term import summary")
    for key, value in counters.items():
        print(f"{key}: {value}")
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
