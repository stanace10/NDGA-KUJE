from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.academics.models import AcademicClass, AcademicSession, StudentClassEnrollment, StudentSubjectEnrollment, Term, TeacherSubjectAssignment
from apps.academics.term_policy import (
    class_is_external_exam_class_for_term,
    exclude_external_exam_classes_for_term,
)
from apps.academics.subject_policy import exclude_non_result_subjects
from apps.academics.grade_scale import is_failing_grade
from apps.accounts.models import User
from apps.dashboard.intelligence import build_student_academic_analytics, build_teacher_performance_analytics
from apps.dashboard.models import SchoolProfile
from apps.setup_wizard.models import AcademicOperationWindow
from apps.setup_wizard.services import get_academic_window_state
from apps.results.insights import build_result_comment_bundle
from apps.results.models import (
    ClassCompilationStatus,
    ClassResultCompilation,
    ResultAccessPin,
    ResultSheet,
    ResultSheetStatus,
    StudentSubjectScore,
)

TERM_ORDER = {"FIRST": 1, "SECOND": 2, "THIRD": 3}
COMPONENT_LEADERBOARD_FIELDS = (
    ("ca1", "CA 1"),
    ("ca23", "CA 2 + CA 3"),
    ("ca4", "Assignment / Projects / Practical"),
    ("class_participation", "Class Participation"),
    ("objective", "Objective"),
    ("theory", "Theory"),
    ("total_exam", "Exam"),
    ("grand_total", "Overall Total"),
)
RESULT_COMPONENTS = {
    "ca1": ("CA1", AcademicOperationWindow.WindowType.RESULT_CA1),
    "ca23": ("CA2/CA3", AcademicOperationWindow.WindowType.RESULT_CA23),
    "ca4": ("Assignment / Projects / Practical", AcademicOperationWindow.WindowType.RESULT_CA4),
    "exam": ("Exam", AcademicOperationWindow.WindowType.RESULT_EXAM),
}
SUBMITTED_COMPONENT_STATUSES = {"SUBMITTED_TO_DEAN", "APPROVED_BY_DEAN"}


def _component_review_status(sheet, component_key):
    if sheet is None:
        return "DRAFT"
    raw = sheet.cbt_component_policies or {}
    review = raw.get("review") if isinstance(raw, dict) else {}
    row = review.get(component_key) if isinstance(review, dict) else {}
    return (row or {}).get("status") or "DRAFT"


def _expired_result_components():
    expired = {}
    for key, (_label, window_type) in RESULT_COMPONENTS.items():
        state = get_academic_window_state(window_type=window_type)
        expired[key] = state["status"] == "EXPIRED"
    return expired


def _to_float(value, digits=2):
    return round(float(value or 0), digits)


FIXED_CLASS_SUBJECT_COUNTS = {
    "JS1": 16,
    "JS2": 17,
    "SS1": 14,
    "SS2": 13,
}

HISTORICAL_TERM_CLASS_SUBJECT_COUNTS = {
    ("2025/2026", "FIRST", "JS1"): 18,
}


def _fixed_subject_count_for_class(academic_class, *, session=None, term=None):
    if academic_class is None:
        return None
    instructional = academic_class.instructional_class
    code = (getattr(instructional, "code", "") or "").strip().upper()
    session_name = (getattr(session, "name", "") or "").strip()
    term_name = (getattr(term, "name", "") or "").strip().upper()
    historical_count = HISTORICAL_TERM_CLASS_SUBJECT_COUNTS.get((session_name, term_name, code))
    if historical_count:
        return historical_count
    return FIXED_CLASS_SUBJECT_COUNTS.get(code)


def _score_component_value(score, field_name):
    if field_name == "ca23":
        return (score.ca2 or Decimal("0.00")) + (score.ca3 or Decimal("0.00"))
    return getattr(score, field_name, Decimal("0.00")) or Decimal("0.00")


def _period_key(session, term):
    if session is None or term is None:
        return (0, 0)
    return (session.id, TERM_ORDER.get(getattr(term, "name", ""), 99))


def previous_window(*, session, term):
    if session is None or term is None:
        return None, None
    terms = list(Term.objects.filter(session=session))
    terms.sort(key=lambda row: TERM_ORDER.get(row.name, 99))
    for index, row in enumerate(terms):
        if row.id != term.id:
            continue
        if index > 0:
            return session, terms[index - 1]
        previous_session = AcademicSession.objects.exclude(id=session.id).order_by("-name", "-id").first()
        if not previous_session:
            return None, None
        previous_terms = list(Term.objects.filter(session=previous_session))
        previous_terms.sort(key=lambda item: TERM_ORDER.get(item.name, 99))
        return (previous_session, previous_terms[-1]) if previous_terms else (None, None)
    return None, None


def _student_map(student_ids):
    students = User.objects.select_related("student_profile").filter(id__in=student_ids)
    return {row.id: row for row in students}


def _enrollment_map(*, student_ids, session):
    rows = (
        StudentClassEnrollment.objects.select_related("academic_class")
        .filter(student_id__in=student_ids, session=session, is_active=True)
        .order_by("-updated_at", "-id")
    )
    payload = {}
    for row in rows:
        payload.setdefault(row.student_id, row)
    return payload


def _student_label(student):
    return student.get_full_name() or student.display_name or student.username


def _fallback_compilation_for_student(*, student, session=None, term=None):
    score_qs = StudentSubjectScore.objects.filter(student=student).select_related(
        "result_sheet__session",
        "result_sheet__term",
        "result_sheet__academic_class",
    )
    score_qs = exclude_non_result_subjects(score_qs, field_name="result_sheet__subject")
    if session is not None:
        score_qs = score_qs.filter(result_sheet__session=session)
    if term is not None:
        score_qs = score_qs.filter(result_sheet__term=term)
    latest_score = score_qs.order_by("-result_sheet__session__id", "-result_sheet__term__id", "-id").first()
    if latest_score is None:
        return None

    resolved_session = session or latest_score.result_sheet.session
    resolved_term = term or latest_score.result_sheet.term
    enrollment = (
        StudentClassEnrollment.objects.select_related("academic_class")
        .filter(student=student, session=resolved_session, is_active=True)
        .order_by("-updated_at", "-id")
        .first()
    )
    academic_class = None
    if enrollment is not None:
        academic_class = enrollment.academic_class
    elif latest_score.result_sheet.academic_class_id:
        academic_class = latest_score.result_sheet.academic_class.base_class or latest_score.result_sheet.academic_class
    if academic_class is None:
        return None

    compilation = (
        ClassResultCompilation.objects.filter(
            academic_class=academic_class,
            session=resolved_session,
            term=resolved_term,
        )
        .select_related("academic_class", "session", "term")
        .first()
    )
    if compilation is not None:
        return compilation

    return ClassResultCompilation(
        academic_class=academic_class,
        session=resolved_session,
        term=resolved_term,
        status=ClassCompilationStatus.DRAFT,
    )


def build_result_upload_statistics(*, session, term, academic_class=None, teacher=None):
    if session is None or term is None:
        return {
            "available": False,
            "teacher_rows": [],
            "class_rows": [],
            "not_submitted_rows": [],
            "dean_pending_rows": [],
            "form_pending_rows": [],
            "vp_pending_rows": [],
            "summary": {},
        }

    instructional_class = academic_class.instructional_class if academic_class else None
    assignments_qs = TeacherSubjectAssignment.objects.filter(session=session, term=term, is_active=True)
    assignments_qs = exclude_non_result_subjects(assignments_qs, field_name="subject")
    assignments_qs = exclude_external_exam_classes_for_term(assignments_qs, term, field_name="academic_class")
    if instructional_class is not None:
        assignments_qs = assignments_qs.filter(academic_class=instructional_class)
    if teacher is not None:
        assignments_qs = assignments_qs.filter(teacher=teacher)
    assignments = list(
        assignments_qs.select_related("teacher", "teacher__staff_profile", "academic_class", "subject")
        .order_by("academic_class__code", "subject__name")
    )

    assignment_lookup = {(row.academic_class_id, row.subject_id): row for row in assignments}
    sheet_qs = ResultSheet.objects.filter(session=session, term=term).select_related("academic_class", "subject")
    sheet_qs = exclude_non_result_subjects(sheet_qs, field_name="subject")
    sheet_qs = exclude_external_exam_classes_for_term(sheet_qs, term, field_name="academic_class")
    if instructional_class is not None:
        sheet_qs = sheet_qs.filter(academic_class=instructional_class)
    elif assignments:
        class_ids = {row.academic_class_id for row in assignments}
        subject_ids = {row.subject_id for row in assignments}
        sheet_qs = sheet_qs.filter(academic_class_id__in=class_ids, subject_id__in=subject_ids)
    sheet_map = {(row.academic_class_id, row.subject_id): row for row in sheet_qs}
    expired_components = _expired_result_components()

    teacher_stats = {}
    class_stats = {}
    for assignment in assignments:
        sheet = sheet_map.get((assignment.academic_class_id, assignment.subject_id))
        teacher_row = teacher_stats.setdefault(
            assignment.teacher_id,
            {
                "teacher": assignment.teacher,
                "staff_name": _student_label(assignment.teacher),
                "staff_id": getattr(getattr(assignment.teacher, "staff_profile", None), "staff_id", assignment.teacher.username),
                "role_code": assignment.teacher.primary_role.code if assignment.teacher.primary_role_id else "-",
                "subject_workload": 0,
                "draft_count": 0,
                "submitted_count": 0,
                "dean_approved_count": 0,
                "published_count": 0,
                "deadline_flags": 0,
                "deadline_flag_details": [],
                "subjects": set(),
                "classes": set(),
            },
        )
        teacher_row["subject_workload"] += 1
        teacher_row["subjects"].add(assignment.subject.name)
        teacher_row["classes"].add(assignment.academic_class.display_name or assignment.academic_class.code)

        class_row = class_stats.setdefault(
            assignment.academic_class_id,
            {
                "academic_class": assignment.academic_class,
                "class_name": assignment.academic_class.display_name or assignment.academic_class.code,
                "class_level": assignment.academic_class.level_display_name,
                "workload": 0,
                "completed": 0,
            },
        )
        class_row["workload"] += 1

        status = sheet.status if sheet else ResultSheetStatus.DRAFT
        for component_key, is_expired in expired_components.items():
            if not is_expired:
                continue
            if _component_review_status(sheet, component_key) not in SUBMITTED_COMPONENT_STATUSES:
                teacher_row["deadline_flags"] += 1
                teacher_row["deadline_flag_details"].append(
                    f"{RESULT_COMPONENTS[component_key][0]} {assignment.academic_class.code} {assignment.subject.name}"
                )
        if status == ResultSheetStatus.DRAFT:
            teacher_row["draft_count"] += 1
        else:
            teacher_row["submitted_count"] += 1
            class_row["completed"] += 1
        if status in {
            ResultSheetStatus.APPROVED_BY_DEAN,
            ResultSheetStatus.COMPILED_BY_FORM_TEACHER,
            ResultSheetStatus.SUBMITTED_TO_VP,
            ResultSheetStatus.REJECTED_BY_VP,
            ResultSheetStatus.PUBLISHED,
        }:
            teacher_row["dean_approved_count"] += 1
        if status == ResultSheetStatus.PUBLISHED:
            teacher_row["published_count"] += 1

    teacher_rows = []
    for row in teacher_stats.values():
        workload = row["subject_workload"] or 1
        row["completion_rate"] = round((row["submitted_count"] / workload) * 100, 2)
        row["subjects"] = sorted(row["subjects"])
        row["classes"] = sorted(row["classes"])
        row["deadline_flag_details"] = sorted(row["deadline_flag_details"])
        teacher_rows.append(row)
    teacher_rows.sort(key=lambda item: (-item["completion_rate"], item["staff_name"].lower()))

    class_rows = []
    for row in class_stats.values():
        workload = row["workload"] or 1
        row["completion_rate"] = round((row["completed"] / workload) * 100, 2)
        class_rows.append(row)
    class_rows.sort(key=lambda item: (-item["completion_rate"], item["class_name"].lower()))

    relevant_class_ids = {row.academic_class_id for row in assignments}
    compilation_qs = ClassResultCompilation.objects.filter(session=session, term=term)
    if instructional_class is not None:
        compilation_qs = compilation_qs.filter(academic_class=instructional_class)
    elif relevant_class_ids:
        compilation_qs = compilation_qs.filter(academic_class_id__in=relevant_class_ids)

    dean_pending_rows = []
    for row in sheet_qs.filter(status=ResultSheetStatus.SUBMITTED_TO_DEAN).order_by("academic_class__code", "subject__name"):
        assignment = assignment_lookup.get((row.academic_class_id, row.subject_id))
        dean_pending_rows.append(
            {
                "class_name": row.academic_class.display_name or row.academic_class.code,
                "subject_name": row.subject.name,
                "teacher_name": _student_label(assignment.teacher) if assignment else "-",
            }
        )

    form_pending_rows = [
        {
            "class_name": row.academic_class.display_name or row.academic_class.code,
            "status": row.get_status_display(),
        }
        for row in compilation_qs.select_related("academic_class")
        .filter(status__in=[ClassCompilationStatus.DRAFT, ClassCompilationStatus.REJECTED_BY_VP])
        .order_by("academic_class__code")
    ]
    vp_pending_rows = [
        {
            "class_name": row.academic_class.display_name or row.academic_class.code,
            "status": row.get_status_display(),
        }
        for row in compilation_qs.select_related("academic_class")
        .filter(status=ClassCompilationStatus.SUBMITTED_TO_VP)
        .order_by("academic_class__code")
    ]

    not_submitted_rows = [row for row in teacher_rows if row["completion_rate"] < 100]
    summary = {
        "teacher_count": len(teacher_rows),
        "class_count": len(class_rows),
        "dean_review_pending": len(dean_pending_rows),
        "form_compilation_pending": len(form_pending_rows),
        "vp_publish_pending": len(vp_pending_rows),
        "published_compilations": compilation_qs.filter(status=ClassCompilationStatus.PUBLISHED).count(),
        "not_submitted_teachers": len(not_submitted_rows),
    }
    return {
        "available": True,
        "teacher_rows": teacher_rows,
        "class_rows": class_rows,
        "not_submitted_rows": not_submitted_rows,
        "dean_pending_rows": dean_pending_rows,
        "form_pending_rows": form_pending_rows,
        "vp_pending_rows": vp_pending_rows,
        "summary": summary,
    }


def build_teacher_ranking(*, session, term):
    if session is None or term is None:
        return {"available": False, "rows": []}
    teacher_ids = list(
        exclude_external_exam_classes_for_term(
            TeacherSubjectAssignment.objects.filter(session=session, term=term, is_active=True),
            term,
            field_name="academic_class",
        )
        .values_list("teacher_id", flat=True)
        .distinct()
    )
    assignments = list(
        exclude_external_exam_classes_for_term(
            TeacherSubjectAssignment.objects.filter(session=session, term=term, is_active=True),
            term,
            field_name="academic_class",
        ).select_related("academic_class", "subject")
    )
    sheet_map = {
        (row.academic_class_id, row.subject_id): row
        for row in ResultSheet.objects.filter(
            session=session,
            term=term,
            academic_class_id__in={row.academic_class_id for row in assignments},
            subject_id__in={row.subject_id for row in assignments},
        )
    }
    expired_components = _expired_result_components()
    teacher_deadline_flags = defaultdict(list)
    for assignment in assignments:
        sheet = sheet_map.get((assignment.academic_class_id, assignment.subject_id))
        for component_key, is_expired in expired_components.items():
            if not is_expired:
                continue
            if _component_review_status(sheet, component_key) not in SUBMITTED_COMPONENT_STATUSES:
                teacher_deadline_flags[assignment.teacher_id].append(
                    f"{RESULT_COMPONENTS[component_key][0]} {assignment.academic_class.code} {assignment.subject.name}"
                )
    rows = []
    for teacher in User.objects.select_related("staff_profile", "primary_role").filter(id__in=teacher_ids):
        analytics = build_teacher_performance_analytics(
            teacher=teacher,
            current_session=session,
            current_term=term,
        )
        if not analytics.get("available"):
            continue
        flags = sorted(teacher_deadline_flags.get(teacher.id, []))
        deadline_penalty = min(len(flags) * 2, 20)
        rows.append(
            {
                "teacher": teacher,
                "staff_name": _student_label(teacher),
                "staff_id": getattr(getattr(teacher, "staff_profile", None), "staff_id", teacher.username),
                "effectiveness_score": max(round(analytics["effectiveness_score"] - deadline_penalty, 2), 0),
                "base_effectiveness_score": analytics["effectiveness_score"],
                "deadline_flags": len(flags),
                "deadline_penalty": deadline_penalty,
                "deadline_flag_details": flags,
                "exam_pass_rate": analytics["exam_pass_rate"],
                "class_engagement": analytics["class_engagement"],
                "cbt_completion_rate": analytics["cbt_completion_rate"],
                "student_improvement": analytics["student_improvement"],
                "assigned_classes": analytics["assigned_classes"],
                "assigned_subjects": analytics["assigned_subjects"],
            }
        )
    rows.sort(key=lambda item: (-item["effectiveness_score"], item["staff_name"].lower()))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return {"available": True, "rows": rows}


def _student_average_rows(*, session, term, academic_class=None):
    score_qs = StudentSubjectScore.objects.filter(result_sheet__session=session, result_sheet__term=term)
    score_qs = exclude_non_result_subjects(score_qs, field_name="result_sheet__subject")
    score_qs = exclude_external_exam_classes_for_term(score_qs, term, field_name="result_sheet__academic_class")
    if academic_class is not None:
        if class_is_external_exam_class_for_term(academic_class, term):
            return []
        instructional_class = academic_class.instructional_class
        class_ids = academic_class.cohort_class_ids()
        student_ids = list(
            StudentClassEnrollment.objects.filter(
                academic_class_id__in=class_ids,
                session=session,
                is_active=True,
            ).values_list("student_id", flat=True)
        )
        active_pairs = set(
            StudentSubjectEnrollment.objects.filter(
                student_id__in=student_ids,
                session=session,
                is_active=True,
            ).values_list("student_id", "subject_id")
        )
        totals = defaultdict(Decimal)
        counts = defaultdict(int)
        for score in score_qs.filter(
            student_id__in=student_ids,
            result_sheet__academic_class=instructional_class,
        ).select_related("result_sheet"):
            pair = (score.student_id, score.result_sheet.subject_id)
            if active_pairs and pair not in active_pairs:
                continue
            totals[score.student_id] += score.grand_total or Decimal("0.00")
            counts[score.student_id] += 1
        score_rows = [
            {
                "student_id": student_id,
                "total": total,
                "subject_count": counts[student_id],
                "average": None,
            }
            for student_id, total in totals.items()
        ]
    else:
        score_rows = list(
            score_qs.values("student_id").annotate(total=Sum("grand_total"), subject_count=Count("id"), average=Avg("grand_total"))
        )
        student_ids = [row["student_id"] for row in score_rows]
    student_map = _student_map(student_ids)
    enrollment_map = _enrollment_map(student_ids=student_ids, session=session)
    allowed_class_ids = set(academic_class.cohort_class_ids()) if academic_class is not None else None
    rows = []
    for row in score_rows:
        student = student_map.get(row["student_id"])
        if student is None:
            continue
        enrollment = enrollment_map.get(student.id)
        if allowed_class_ids is not None and (enrollment is None or enrollment.academic_class_id not in allowed_class_ids):
            continue
        subject_count = int(row.get("subject_count") or 0)
        denominator = subject_count
        total = Decimal(row.get("total") or 0)
        average = (total / Decimal(denominator)) if denominator else Decimal("0.00")
        rows.append(
            {
                "student": student,
                "student_name": _student_label(student),
                "student_number": getattr(getattr(student, "student_profile", None), "student_number", student.username),
                "class_name": (enrollment.academic_class.display_name or enrollment.academic_class.code) if enrollment else "-",
                "level_name": enrollment.academic_class.level_display_name if enrollment else "-",
                "total": _to_float(total),
                "subject_count": denominator,
                "actual_subject_count": subject_count,
                "average": _to_float(average),
            }
        )
    rows.sort(key=lambda item: (-item["average"], -item["total"], item["student_name"].lower()))
    previous_rank = 0
    previous_score = None
    for index, row in enumerate(rows, start=1):
        score_key = (row["average"], row["total"])
        if score_key != previous_score:
            previous_rank = index
            previous_score = score_key
        row["position"] = previous_rank
    return rows


def build_award_listing(*, session, term, academic_class=None):
    if session is None or term is None:
        return {"available": False}

    student_rows = _student_average_rows(session=session, term=term, academic_class=academic_class)
    if not student_rows:
        return {
            "available": False,
            "top_three": [],
            "top_five": [],
            "best_in_class": [],
            "best_in_level": [],
            "best_in_subject": [],
            "most_improved": [],
            "top_students": [],
        }

    prev_session, prev_term = previous_window(session=session, term=term)
    previous_map = {}
    if prev_session and prev_term:
        for row in _student_average_rows(session=prev_session, term=prev_term, academic_class=academic_class):
            previous_map[row["student"].id] = row
    most_improved = []
    for row in student_rows:
        previous = previous_map.get(row["student"].id)
        if previous is None:
            continue
        delta = round(row["average"] - previous["average"], 2)
        most_improved.append({**row, "delta": delta})
    most_improved.sort(key=lambda item: (-item["delta"], -item["average"], item["student_name"].lower()))

    filtered_student_ids = {row["student"].id for row in student_rows}
    subject_qs = StudentSubjectScore.objects.filter(
        result_sheet__session=session,
        result_sheet__term=term,
        student_id__in=filtered_student_ids,
    )
    subject_qs = exclude_non_result_subjects(subject_qs, field_name="result_sheet__subject")
    if academic_class is not None:
        subject_qs = subject_qs.filter(result_sheet__academic_class=academic_class.instructional_class)

    best_in_subject = []
    grouped_subjects = defaultdict(list)
    for row in subject_qs.values("result_sheet__subject__name", "student_id").annotate(score=Avg("grand_total")):
        grouped_subjects[row["result_sheet__subject__name"]].append(row)
    student_map = _student_map({row["student_id"] for items in grouped_subjects.values() for row in items})
    enrollment_map = _enrollment_map(student_ids=student_map.keys(), session=session)
    for subject_name, items in grouped_subjects.items():
        items.sort(key=lambda item: (-float(item["score"] or 0), item["student_id"]))
        winner = items[0]
        student = student_map.get(winner["student_id"])
        if student is None:
            continue
        enrollment = enrollment_map.get(student.id)
        best_in_subject.append(
            {
                "subject": subject_name,
                "student_name": _student_label(student),
                "student_number": getattr(getattr(student, "student_profile", None), "student_number", student.username),
                "class_name": (enrollment.academic_class.display_name or enrollment.academic_class.code) if enrollment else "-",
                "level_name": enrollment.academic_class.level_display_name if enrollment else "-",
                "score": _to_float(winner["score"]),
            }
        )
    best_in_subject.sort(key=lambda item: item["subject"].lower())

    subject_leaderboards = []
    for subject_name, items in grouped_subjects.items():
        ranked_rows = []
        previous_rank = 0
        previous_score = None
        for index, item in enumerate(sorted(items, key=lambda row: (-float(row["score"] or 0), row["student_id"])), start=1):
            score_value = _to_float(item["score"])
            if score_value != previous_score:
                previous_rank = index
                previous_score = score_value
            student = student_map.get(item["student_id"])
            if student is None:
                continue
            enrollment = enrollment_map.get(student.id)
            ranked_rows.append(
                {
                    "position": previous_rank,
                    "student_name": _student_label(student),
                    "student_number": getattr(getattr(student, "student_profile", None), "student_number", student.username),
                    "class_name": (enrollment.academic_class.display_name or enrollment.academic_class.code) if enrollment else "-",
                    "score": score_value,
                }
            )
            if len(ranked_rows) >= 5:
                break
        subject_leaderboards.append({"subject": subject_name, "rows": ranked_rows})
    subject_leaderboards.sort(key=lambda item: item["subject"].lower())

    best_in_class = []
    best_in_level = []
    grouped_classes = defaultdict(list)
    grouped_levels = defaultdict(list)
    for row in student_rows:
        grouped_classes[row["class_name"]].append(row)
        grouped_levels[row["level_name"]].append(row)
    for class_name, items in grouped_classes.items():
        items.sort(key=lambda item: (-item["average"], -item["total"], item["student_name"].lower()))
        best_in_class.append({"class_name": class_name, **items[0]})
    best_in_class.sort(key=lambda item: item["class_name"].lower())
    for level_name, items in grouped_levels.items():
        items.sort(key=lambda item: (-item["average"], -item["total"], item["student_name"].lower()))
        best_in_level.append({"level_name": level_name, **items[0]})
    best_in_level.sort(key=lambda item: item["level_name"].lower())

    return {
        "available": True,
        "top_three": student_rows[:3],
        "top_five": student_rows[:5],
        "best_in_class": best_in_class,
        "best_in_level": best_in_level,
        "best_in_subject": best_in_subject,
        "most_improved": most_improved[:5],
        "top_students": student_rows[:10],
        "position_board": student_rows[:25],
        "subject_leaderboards": subject_leaderboards,
    }


def build_class_performance_snapshot(*, session, term, academic_class=None):
    if session is None or term is None:
        return {"available": False}

    student_rows = _student_average_rows(session=session, term=term, academic_class=academic_class)
    if not student_rows:
        return {
            "available": False,
            "scope_label": "Selected Class" if academic_class is not None else "All Classes",
            "position_rows": [],
            "component_subject_winners": [],
        }

    filtered_student_ids = {row["student"].id for row in student_rows}
    score_qs = StudentSubjectScore.objects.filter(
        result_sheet__session=session,
        result_sheet__term=term,
        student_id__in=filtered_student_ids,
    ).select_related("student__student_profile", "result_sheet__subject")
    score_qs = exclude_non_result_subjects(score_qs, field_name="result_sheet__subject")
    score_qs = exclude_external_exam_classes_for_term(score_qs, term, field_name="result_sheet__academic_class")
    if academic_class is not None:
        score_qs = score_qs.filter(result_sheet__academic_class=academic_class.instructional_class)

    score_rows = list(score_qs)
    enrollment_map = _enrollment_map(student_ids=filtered_student_ids, session=session)
    component_subject_winners = []
    for field_name, label in COMPONENT_LEADERBOARD_FIELDS:
        subject_rows = []
        subject_buckets = defaultdict(list)
        for row in score_rows:
            subject_buckets[row.result_sheet.subject.name].append(row)
        for subject_name, items in subject_buckets.items():
            ranked_items = sorted(
                items,
                key=lambda item: (
                    -float(_score_component_value(item, field_name)),
                    _student_label(item.student).lower(),
                    item.student_id,
                ),
            )
            winner = ranked_items[0] if ranked_items else None
            if winner is None:
                continue
            winner_score = _to_float(_score_component_value(winner, field_name))
            if winner_score <= 0:
                continue
            component_scores = [_score_component_value(item, field_name) for item in items]
            enrollment = enrollment_map.get(winner.student_id)
            subject_rows.append(
                {
                    "subject": subject_name,
                    "student_name": _student_label(winner.student),
                    "student_number": getattr(
                        getattr(winner.student, "student_profile", None),
                        "student_number",
                        winner.student.username,
                    ),
                    "class_name": (
                        enrollment.academic_class.display_name or enrollment.academic_class.code
                    ) if enrollment else "-",
                    "score": winner_score,
                    "average": _to_float(sum(component_scores) / len(component_scores)) if component_scores else 0,
                }
            )
        if subject_rows:
            component_subject_winners.append(
                {
                    "key": field_name,
                    "label": label,
                    "rows": sorted(subject_rows, key=lambda item: item["subject"].lower()),
                }
            )

    overall_best = student_rows[0]
    highest_total = sorted(
        student_rows,
        key=lambda item: (-item["total"], -item["average"], item["student_name"].lower()),
    )[0]
    class_average = _to_float(sum(row["average"] for row in student_rows) / len(student_rows))
    total_average = _to_float(sum(row["total"] for row in student_rows) / len(student_rows))
    if academic_class is None:
        scope_label = "All Classes"
    elif academic_class.base_class_id:
        scope_label = f"{academic_class.display_name or academic_class.code} Class Arm"
    else:
        scope_label = f"{academic_class.display_name or academic_class.code} Class Level"
    return {
        "available": True,
        "scope_label": scope_label,
        "student_count": len(student_rows),
        "subject_count": len({row.result_sheet.subject_id for row in score_rows}),
        "overall_best": overall_best,
        "highest_total": highest_total,
        "class_average": class_average,
        "total_average": total_average,
        "position_rows": student_rows,
        "component_subject_winners": component_subject_winners,
    }


def build_student_performance_report(*, student, session=None, term=None):
    compilation_qs = ClassResultCompilation.objects.filter(
        status=ClassCompilationStatus.PUBLISHED,
        student_records__student=student,
    )
    if session is not None:
        compilation_qs = compilation_qs.filter(session=session)
    if term is not None:
        compilation_qs = compilation_qs.filter(term=term)
    compilation = (
        compilation_qs.select_related("academic_class", "session", "term")
        .order_by("-session__name", "-term__name", "-updated_at")
        .first()
    )
    if compilation is None:
        compilation = _fallback_compilation_for_student(student=student, session=session, term=term)
    if compilation is None:
        return {"available": False}
    if class_is_external_exam_class_for_term(compilation.academic_class, compilation.term):
        return {"available": False}

    record = compilation.student_records.filter(student=student).first() if compilation.pk else None
    attendance_percentage = Decimal(str(getattr(record, "attendance_percentage", 0) or 0)).quantize(Decimal("0.01"))
    school_profile = SchoolProfile.load()

    cohort_student_ids = list(
        StudentClassEnrollment.objects.filter(
            academic_class=compilation.academic_class,
            session=compilation.session,
            is_active=True,
        ).values_list("student_id", flat=True)
    )
    if not cohort_student_ids and compilation.pk:
        cohort_student_ids = list(compilation.student_records.values_list("student_id", flat=True))
    if not cohort_student_ids:
        cohort_student_ids = [student.id]
    performance_score_qs = StudentSubjectScore.objects.filter(
        student_id__in=cohort_student_ids,
        result_sheet__session=compilation.session,
        result_sheet__term=compilation.term,
        result_sheet__academic_class=compilation.academic_class.instructional_class,
    )
    performance_score_qs = exclude_non_result_subjects(
        performance_score_qs,
        field_name="result_sheet__subject",
    )
    score_rows = list(
        exclude_external_exam_classes_for_term(
            performance_score_qs,
            compilation.term,
            field_name="result_sheet__academic_class",
        )
        .select_related("result_sheet__subject")
        .order_by("result_sheet__subject__name")
    )
    subject_buckets = defaultdict(list)
    for row in score_rows:
        subject_buckets[row.result_sheet.subject.name].append(row)

    current_rows = []
    for subject_name, items in subject_buckets.items():
        current = next((row for row in items if row.student_id == student.id), None)
        if current is None:
            continue
        scores = [float(row.grand_total or 0) for row in items]
        score_value = _to_float(current.grand_total)
        current_rows.append(
            {
                "subject": subject_name,
                "score": score_value,
                "highest": round(max(scores), 2) if scores else 0,
                "lowest": round(min(scores), 2) if scores else 0,
                "average": round(sum(scores) / len(scores), 2) if scores else 0,
                "grade": current.grade or "-",
                "remark": "Excellent" if score_value >= 70 else ("Good" if score_value >= 50 else "Needs Support"),
            }
        )
    current_rows.sort(key=lambda item: item["subject"].lower())

    strongest_subjects = sorted(current_rows, key=lambda item: (-item["score"], item["subject"].lower()))[:3]

    class_rows = _student_average_rows(session=compilation.session, term=compilation.term, academic_class=compilation.academic_class)
    highest_average = class_rows[0]["average"] if class_rows else 0
    lowest_average = class_rows[-1]["average"] if class_rows else 0
    class_average = _to_float(sum(row["average"] for row in class_rows) / len(class_rows)) if class_rows else 0
    student_average_row = next((row for row in class_rows if row["student"].id == student.id), None)
    student_average = student_average_row["average"] if student_average_row else 0
    average_gap_to_top = round(float(highest_average or 0) - float(student_average or 0), 2)
    average_gap_from_class = round(float(student_average or 0) - float(class_average or 0), 2)

    historical_compilations = list(
        ClassResultCompilation.objects.filter(
            status=ClassCompilationStatus.PUBLISHED,
            student_records__student=student,
        )
        .select_related("academic_class", "session", "term")
        .distinct()
    )
    historical_compilations.sort(key=lambda row: _period_key(row.session, row.term))
    rank_trend_rows = []
    for row in historical_compilations:
        rank_rows = _student_average_rows(session=row.session, term=row.term, academic_class=row.academic_class)
        matched = next((item for item in rank_rows if item["student"].id == student.id), None)
        if matched is None:
            continue
        rank_trend_rows.append(
            {
                "label": f"{row.session.name} {row.term.get_name_display()}",
                "position": matched["position"],
                "average": matched["average"],
                "class_name": matched["class_name"],
            }
        )
    improvement_delta = 0.0
    previous_term_label = ""
    if len(rank_trend_rows) >= 2:
        improvement_delta = round(rank_trend_rows[-1]["average"] - rank_trend_rows[-2]["average"], 2)
        previous_term_label = rank_trend_rows[-2]["label"]

    analytics = build_student_academic_analytics(
        student=student,
        current_session=compilation.session,
        current_term=compilation.term,
    )
    weak_subjects = [row["subject"] for row in analytics.get("weak_subjects", [])]
    comment_bundle = build_result_comment_bundle(
        student_name=_student_label(student),
        average_score=Decimal(str(student_average or 0)),
        attendance_percentage=attendance_percentage,
        fail_count=len([row for row in current_rows if is_failing_grade(row["grade"])]),
        weak_subjects=weak_subjects,
        predicted_score=(analytics.get("prediction") or {}).get("score"),
        risk_label=(analytics.get("risk") or {}).get("label"),
        strongest_subjects=[row["subject"] for row in strongest_subjects],
        improvement_delta=improvement_delta,
        teacher_guidance=school_profile.teacher_comment_guidance or school_profile.auto_comment_guidance,
        dean_guidance=school_profile.dean_comment_guidance or school_profile.auto_comment_guidance,
        principal_guidance=school_profile.principal_comment_guidance or school_profile.auto_comment_guidance,
    )
    principal_comment = (
        (getattr(record, "principal_comment", "") or "").strip()
        or (getattr(compilation, "decision_comment", "") or "").strip()
        or comment_bundle["principal_comment"]
    )

    if student_average >= 75:
        performance_band = "Outstanding"
    elif student_average >= 60:
        performance_band = "Strong"
    elif student_average >= 50:
        performance_band = "Steady"
    else:
        performance_band = "Intervention Required"

    subject_strength_summary = (
        f"Strongest subjects: {', '.join(row['subject'] for row in strongest_subjects)}."
        if strongest_subjects
        else "No strong subject cluster is available yet."
    )
    watch_summary = (
        f"Watch subjects: {', '.join(weak_subjects[:3])}."
        if weak_subjects
        else "No urgent watch subject flagged for this student."
    )

    return {
        "available": True,
        "compilation": compilation,
        "is_preview": compilation.status != ClassCompilationStatus.PUBLISHED or not bool(compilation.pk),
        "student": student,
        "analytics": analytics,
        "teacher_comment": getattr(record, "teacher_comment", "") if record else "",
        "principal_comment": principal_comment,
        "subject_rows": current_rows,
        "strongest_subjects": strongest_subjects,
        "subject_strength_summary": subject_strength_summary,
        "highest_average": highest_average,
        "student_average": student_average,
        "lowest_average": lowest_average,
        "class_average": class_average,
        "average_gap_to_top": average_gap_to_top,
        "average_gap_from_class": average_gap_from_class,
        "attendance_percentage": _to_float(attendance_percentage),
        "performance_band": performance_band,
        "class_rows": class_rows,
        "class_position": student_average_row["position"] if student_average_row else None,
        "rank_trend_rows": rank_trend_rows,
        "previous_term_label": previous_term_label,
        "improvement_delta": improvement_delta,
        "watch_subjects": weak_subjects,
        "watch_summary": watch_summary,
        "comment_bundle": comment_bundle,
    }


def active_result_pin_for_student(*, student, session, term):
    pin = ResultAccessPin.objects.filter(student=student, session=session, term=term, is_active=True).order_by("-created_at").first()
    if pin and pin.is_usable():
        return pin
    return None
