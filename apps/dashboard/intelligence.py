from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum

from apps.academics.models import StudentClassEnrollment, StudentSubjectEnrollment, TeacherSubjectAssignment
from apps.accounts.constants import ROLE_STUDENT
from apps.accounts.models import User
from apps.cbt.models import CBTAttemptStatus, Exam, ExamAttempt
from apps.finance.services import finance_summary_metrics
from apps.results.models import ClassCompilationStatus, ClassResultCompilation, ClassResultStudentRecord, ResultSheet, ResultSheetStatus, StudentSubjectScore

TERM_ORDER = {"FIRST": 1, "SECOND": 2, "THIRD": 3}
GRADE_POINTS = {"A": Decimal("5.0"), "B": Decimal("4.0"), "C": Decimal("3.0"), "D": Decimal("2.0"), "F": Decimal("0.0")}


def _to_float(value, *, digits=2):
    return round(float(value or 0), digits)


def _term_label(session, term):
    if session is None or term is None:
        return "Unknown"
    return f"{session.name} {term.get_name_display()}"


def _session_sort_value(session):
    raw = getattr(session, "name", "") or ""
    match = re.search(r"(20\d{2})", raw)
    if match:
        return int(match.group(1))
    return int(getattr(session, "id", 0) or 0)


def _period_sort_key(session, term):
    return (_session_sort_value(session), TERM_ORDER.get(getattr(term, "name", ""), 99))


def _published_compilations_for_student(student):
    rows = list(
        ClassResultCompilation.objects.filter(
            status=ClassCompilationStatus.PUBLISHED,
            student_records__student=student,
        )
        .select_related("academic_class", "session", "term")
        .distinct()
    )
    rows.sort(key=lambda row: _period_sort_key(row.session, row.term))
    return rows


def _student_subject_rows_for_compilation(student, compilation):
    return list(
        StudentSubjectScore.objects.filter(
            student=student,
            result_sheet__academic_class=compilation.academic_class.instructional_class,
            result_sheet__session=compilation.session,
            result_sheet__term=compilation.term,
        )
        .select_related("result_sheet__subject")
        .order_by("result_sheet__subject__name")
    )


def _student_record_for_compilation(student, compilation):
    return ClassResultStudentRecord.objects.filter(
        compilation=compilation,
        student=student,
    ).first()


def _grade_point(grade):
    return GRADE_POINTS.get((grade or "").strip().upper(), Decimal("0.0"))


def _prediction_band(score):
    value = float(score or 0)
    if value >= 70:
        return "A-range"
    if value >= 60:
        return "B-range"
    if value >= 50:
        return "C-range"
    if value >= 40:
        return "D-range"
    return "At risk"


def _risk_label(score):
    if score >= 75:
        return "Severe"
    if score >= 50:
        return "High"
    if score >= 25:
        return "Moderate"
    return "Low"


def _eligible_students_for_exam(exam):
    enrollment_qs = StudentClassEnrollment.objects.filter(
        session=exam.session,
        academic_class_id__in=exam.academic_class.cohort_class_ids(),
        is_active=True,
    )
    subject_student_ids = list(
        StudentSubjectEnrollment.objects.filter(
            session=exam.session,
            subject=exam.subject,
            is_active=True,
        ).values_list("student_id", flat=True)
    )
    if subject_student_ids:
        enrollment_qs = enrollment_qs.filter(student_id__in=subject_student_ids)
    return enrollment_qs.distinct().count()


def build_student_academic_analytics(*, student, current_session=None, current_term=None):
    compilations = _published_compilations_for_student(student)
    trend_rows = []
    subject_history = defaultdict(list)

    for compilation in compilations:
        score_rows = _student_subject_rows_for_compilation(student, compilation)
        if not score_rows:
            continue
        record = _student_record_for_compilation(student, compilation)
        total_score = sum((Decimal(row.grand_total or 0) for row in score_rows), Decimal("0.00"))
        average_score = (total_score / Decimal(len(score_rows))).quantize(Decimal("0.01"))
        gpa = (sum((_grade_point(row.grade) for row in score_rows), Decimal("0.0")) / Decimal(len(score_rows))).quantize(Decimal("0.01"))
        attendance = Decimal(getattr(record, "attendance_percentage", 0) or 0).quantize(Decimal("0.01"))
        fail_count = len([row for row in score_rows if (row.grade or "F") == "F"])
        row_payload = {
            "label": _term_label(compilation.session, compilation.term),
            "session_id": compilation.session_id,
            "term_id": compilation.term_id,
            "average_score": _to_float(average_score),
            "gpa": _to_float(gpa),
            "attendance": _to_float(attendance),
            "fail_count": fail_count,
        }
        trend_rows.append(row_payload)
        for score in score_rows:
            subject_history[score.result_sheet.subject.name].append(
                {
                    "label": row_payload["label"],
                    "score": _to_float(score.grand_total),
                    "grade": score.grade or "F",
                }
            )

    if not trend_rows:
        return {
            "available": False,
            "trend_rows": [],
            "weak_subjects": [],
            "prediction": {"score": 0.0, "band": "No data"},
            "risk": {"score": 0, "label": "Unknown", "factors": [], "recommendation": "No published results yet."},
            "headline": "No published result analytics yet.",
        }

    selected_row = None
    if current_session and current_term:
        for row in trend_rows:
            if row["session_id"] == current_session.id and row["term_id"] == current_term.id:
                selected_row = row
                break
    if selected_row is None:
        selected_row = trend_rows[-1]

    latest = trend_rows[-1]
    previous = trend_rows[-2] if len(trend_rows) > 1 else None
    average_delta = round(latest["average_score"] - (previous["average_score"] if previous else latest["average_score"]), 2)
    gpa_delta = round(latest["gpa"] - (previous["gpa"] if previous else latest["gpa"]), 2)

    weak_subjects = []
    for subject_name, rows in subject_history.items():
        scores = [row["score"] for row in rows]
        latest_subject_score = scores[-1]
        previous_subject_score = scores[-2] if len(scores) > 1 else scores[-1]
        delta = round(latest_subject_score - previous_subject_score, 2)
        weak_subjects.append(
            {
                "subject": subject_name,
                "average_score": round(sum(scores) / len(scores), 2),
                "latest_score": latest_subject_score,
                "delta": delta,
                "status": "Critical" if latest_subject_score < 50 else ("Watch" if latest_subject_score < 60 else "Stable"),
            }
        )
    weak_subjects.sort(key=lambda row: (row["average_score"], row["subject"].lower()))
    weak_subjects = weak_subjects[:4]

    predicted_score = latest["average_score"]
    if previous:
        predicted_score = (latest["average_score"] * 0.55) + (previous["average_score"] * 0.25) + (latest["attendance"] * 0.20)
    else:
        predicted_score = (latest["average_score"] * 0.8) + (latest["attendance"] * 0.2)
    predicted_score = max(0.0, min(round(predicted_score, 2), 100.0))

    risk_score = 0
    factors = []
    if latest["attendance"] < 60:
        risk_score += 35
        factors.append("Attendance is below 60%.")
    elif latest["attendance"] < 75:
        risk_score += 15
        factors.append("Attendance is below the target 75% threshold.")
    if latest["fail_count"] >= 3:
        risk_score += 30
        factors.append("Multiple subject failures were recorded in the latest term.")
    elif latest["fail_count"] >= 1:
        risk_score += 15
        factors.append("At least one subject failure was recorded in the latest term.")
    if average_delta <= -10:
        risk_score += 20
        factors.append("Average performance dropped sharply from the previous term.")
    elif average_delta <= -5:
        risk_score += 10
        factors.append("Average performance declined compared with the previous term.")
    if latest["average_score"] < 50:
        risk_score += 15
        factors.append("Overall academic average is below pass level.")
    elif latest["average_score"] < 60:
        risk_score += 8
        factors.append("Overall academic average is below strong-credit range.")
    risk_score = min(risk_score, 100)

    recommendation = "Keep current study rhythm and deepen revision in weaker subjects."
    if weak_subjects:
        recommendation = f"Prioritize extra CBT practice and teacher support in {', '.join(row['subject'] for row in weak_subjects[:2])}."
    if _risk_label(risk_score) in {"High", "Severe"}:
        recommendation = "Immediate intervention is recommended: attendance recovery, structured revision timetable, and supervised CBT practice."

    headline = f"{selected_row['label']}: GPA {selected_row['gpa']} with average score {selected_row['average_score']}%."
    if average_delta > 0:
        headline += f" Up {abs(average_delta)} points from the previous term."
    elif average_delta < 0:
        headline += f" Down {abs(average_delta)} points from the previous term."

    return {
        "available": True,
        "trend_rows": trend_rows,
        "current": selected_row,
        "average_delta": average_delta,
        "gpa_delta": gpa_delta,
        "weak_subjects": weak_subjects,
        "prediction": {
            "score": predicted_score,
            "band": _prediction_band(predicted_score),
        },
        "risk": {
            "score": risk_score,
            "label": _risk_label(risk_score),
            "factors": factors,
            "recommendation": recommendation,
        },
        "headline": headline,
    }


def build_teacher_performance_analytics(*, teacher, current_session=None, current_term=None):
    assignment_qs = teacher.subject_assignments.filter(is_active=True)
    if current_session:
        assignment_qs = assignment_qs.filter(session=current_session)
    if current_term:
        assignment_qs = assignment_qs.filter(term=current_term)
    assignments = list(assignment_qs.select_related("academic_class", "subject", "session", "term"))
    if not assignments:
        return {"available": False}

    pair_filter = Q(pk__in=[])
    for assignment in assignments:
        pair_filter |= Q(
            result_sheet__academic_class_id=assignment.academic_class_id,
            result_sheet__subject_id=assignment.subject_id,
            result_sheet__session_id=assignment.session_id,
            result_sheet__term_id=assignment.term_id,
        )
    current_scores = list(
        StudentSubjectScore.objects.filter(pair_filter)
        .select_related("result_sheet__academic_class", "result_sheet__subject", "result_sheet__session", "result_sheet__term")
    )
    score_count = len(current_scores)
    pass_rate = round((len([row for row in current_scores if (row.grade or "F") != "F"]) / score_count) * 100, 2) if score_count else 0.0
    average_score = round(sum((float(row.grand_total or 0) for row in current_scores)) / score_count, 2) if score_count else 0.0

    current_seq = _period_sort_key(current_session, current_term) if current_session and current_term else None
    history_filter = Q(pk__in=[])
    for assignment in assignments:
        history_filter |= Q(
            result_sheet__academic_class_id=assignment.academic_class_id,
            result_sheet__subject_id=assignment.subject_id,
        )
    history_rows = list(
        StudentSubjectScore.objects.filter(history_filter)
        .select_related("result_sheet__academic_class", "result_sheet__subject", "result_sheet__session", "result_sheet__term")
    )
    pair_history = defaultdict(lambda: defaultdict(list))
    for row in history_rows:
        seq = _period_sort_key(row.result_sheet.session, row.result_sheet.term)
        pair_key = (row.result_sheet.academic_class_id, row.result_sheet.subject_id)
        pair_history[pair_key][seq].append(float(row.grand_total or 0))

    improvements = []
    for pair_key, sequence_map in pair_history.items():
        current_values = sequence_map.get(current_seq) if current_seq else None
        if not current_values:
            continue
        previous_sequences = [seq for seq in sequence_map if seq < current_seq]
        if not previous_sequences:
            continue
        previous_seq = max(previous_sequences)
        previous_values = sequence_map.get(previous_seq) or []
        if not previous_values:
            continue
        current_avg = sum(current_values) / len(current_values)
        previous_avg = sum(previous_values) / len(previous_values)
        improvements.append(round(current_avg - previous_avg, 2))
    improvement = round(sum(improvements) / len(improvements), 2) if improvements else 0.0

    cohort_class_ids = sorted({class_id for assignment in assignments for class_id in assignment.academic_class.cohort_class_ids()})
    attendance_qs = ClassResultStudentRecord.objects.filter(compilation__academic_class_id__in=cohort_class_ids)
    if current_session:
        attendance_qs = attendance_qs.filter(compilation__session=current_session)
    if current_term:
        attendance_qs = attendance_qs.filter(compilation__term=current_term)
    class_engagement = _to_float(attendance_qs.aggregate(avg=Avg("attendance_percentage"))["avg"])

    exam_qs = Exam.objects.filter(Q(created_by=teacher) | Q(assignment__teacher=teacher)).distinct()
    if current_session:
        exam_qs = exam_qs.filter(session=current_session)
    if current_term:
        exam_qs = exam_qs.filter(term=current_term)
    exams = list(exam_qs.select_related("academic_class", "subject", "session"))
    eligible_total = 0
    completed_total = 0
    for exam in exams:
        eligible_total += _eligible_students_for_exam(exam)
        completed_total += ExamAttempt.objects.filter(
            exam=exam,
            status__in=[CBTAttemptStatus.SUBMITTED, CBTAttemptStatus.FINALIZED],
        ).values("student_id").distinct().count()
    cbt_completion_rate = round((completed_total / eligible_total) * 100, 2) if eligible_total else 0.0

    improvement_score = max(0.0, min(100.0, round(50 + (improvement * 2), 2)))
    effectiveness_score = round((pass_rate * 0.35) + (class_engagement * 0.2) + (cbt_completion_rate * 0.2) + (improvement_score * 0.25), 2)

    focus_message = "Teacher performance is stable."
    if effectiveness_score >= 75:
        focus_message = "Strong teacher impact across results, attendance, and CBT completion."
    elif pass_rate < 50 or cbt_completion_rate < 50:
        focus_message = "Support is needed on pass rate recovery and CBT participation discipline."

    return {
        "available": True,
        "effectiveness_score": effectiveness_score,
        "average_score": average_score,
        "student_improvement": improvement,
        "exam_pass_rate": pass_rate,
        "class_engagement": class_engagement,
        "cbt_completion_rate": cbt_completion_rate,
        "assignment_count": len(assignments),
        "assigned_classes": sorted({assignment.academic_class.code for assignment in assignments}),
        "assigned_subjects": sorted({assignment.subject.name for assignment in assignments}),
        "focus_message": focus_message,
    }


def build_school_intelligence(*, current_session=None, current_term=None):
    if not current_session:
        return {"available": False}

    total_students = User.objects.filter(primary_role__code=ROLE_STUDENT, is_active=True).count()
    total_staff = User.objects.filter(staff_profile__isnull=False, is_active=True).count()

    current_records = ClassResultStudentRecord.objects.filter(compilation__session=current_session)
    if current_term:
        current_records = current_records.filter(compilation__term=current_term)
    current_attendance = _to_float(current_records.aggregate(avg=Avg("attendance_percentage"))["avg"])

    previous_records = ClassResultStudentRecord.objects.exclude(compilation__session=current_session)
    previous_attendance = _to_float(previous_records.aggregate(avg=Avg("attendance_percentage"))["avg"])
    attendance_delta = round(current_attendance - previous_attendance, 2) if previous_attendance else current_attendance

    score_qs = StudentSubjectScore.objects.filter(result_sheet__session=current_session)
    if current_term:
        score_qs = score_qs.filter(result_sheet__term=current_term)
    weak_subject_rows = list(
        score_qs.values("result_sheet__subject__name")
        .annotate(avg=Avg("grand_total"))
        .order_by("avg", "result_sheet__subject__name")[:5]
    )
    weak_subjects = [
        {
            "subject": row["result_sheet__subject__name"],
            "average_score": _to_float(row["avg"]),
        }
        for row in weak_subject_rows
    ]

    class_summary = []
    class_rows = list(
        score_qs.values("result_sheet__academic_class__code", "result_sheet__academic_class_id")
        .annotate(avg=Avg("grand_total"))
        .order_by("-avg", "result_sheet__academic_class__code")
    )
    for row in class_rows[:5]:
        class_summary.append(
            {
                "class_code": row["result_sheet__academic_class__code"],
                "average_score": _to_float(row["avg"]),
            }
        )
    top_performing_class = class_summary[0] if class_summary else None

    finance_metrics = finance_summary_metrics(session=current_session, term=current_term)
    charged = float(finance_metrics.get("total_charges") or 0)
    paid = float(finance_metrics.get("total_payments") or 0)
    fee_payment_rate = round((paid / charged) * 100, 2) if charged else 100.0

    exam_qs = Exam.objects.filter(session=current_session)
    if current_term:
        exam_qs = exam_qs.filter(term=current_term)
    exams = list(exam_qs.select_related("academic_class", "subject", "session"))
    eligible_total = 0
    completed_total = 0
    for exam in exams:
        eligible_total += _eligible_students_for_exam(exam)
        completed_total += ExamAttempt.objects.filter(
            exam=exam,
            status__in=[CBTAttemptStatus.SUBMITTED, CBTAttemptStatus.FINALIZED],
        ).values("student_id").distinct().count()
    exam_participation_rate = round((completed_total / eligible_total) * 100, 2) if eligible_total else 0.0

    publication_total = ClassResultCompilation.objects.filter(session=current_session)
    if current_term:
        publication_total = publication_total.filter(term=current_term)
    total_compilations = publication_total.count()
    published_compilations = publication_total.filter(status=ClassCompilationStatus.PUBLISHED).count()
    result_publication_rate = round((published_compilations / total_compilations) * 100, 2) if total_compilations else 0.0

    top_students = []
    top_student_rows = list(
        score_qs.values("student_id")
        .annotate(total=Sum("grand_total"), subject_count=Count("id"))
        .order_by("-total", "student_id")[:5]
    )
    if top_student_rows:
        student_ids = [row["student_id"] for row in top_student_rows]
        student_map = {
            row.id: row
            for row in User.objects.select_related("student_profile").filter(id__in=student_ids)
        }
        enrollment_map = {}
        for enrollment in (
            StudentClassEnrollment.objects.select_related("academic_class")
            .filter(student_id__in=student_ids, session=current_session, is_active=True)
            .order_by("-updated_at", "-id")
        ):
            enrollment_map.setdefault(enrollment.student_id, enrollment)
        for row in top_student_rows:
            student = student_map.get(row["student_id"])
            if student is None:
                continue
            subject_count = int(row.get("subject_count") or 0)
            total = Decimal(row.get("total") or 0)
            average_score = (total / Decimal(subject_count)).quantize(Decimal("0.01")) if subject_count else Decimal("0.00")
            enrollment = enrollment_map.get(student.id)
            profile = getattr(student, "student_profile", None)
            top_students.append(
                {
                    "student_name": student.get_full_name() or student.username,
                    "student_number": profile.student_number if profile else student.username,
                    "class_code": (enrollment.academic_class.display_name or enrollment.academic_class.code) if enrollment else "-",
                    "average_score": _to_float(average_score),
                }
            )

    teacher_upload_stats = []
    assignment_qs = TeacherSubjectAssignment.objects.filter(session=current_session, is_active=True)
    if current_term:
        assignment_qs = assignment_qs.filter(term=current_term)
    assignments = list(assignment_qs.select_related("teacher", "teacher__staff_profile", "subject", "academic_class"))
    sheet_map = {
        (row.academic_class_id, row.subject_id): row.status
        for row in ResultSheet.objects.filter(session=current_session, term=current_term)
    }
    teacher_stats = {}
    for assignment in assignments:
        row = teacher_stats.setdefault(
            assignment.teacher_id,
            {
                "staff_name": assignment.teacher.get_full_name() or assignment.teacher.username,
                "staff_id": getattr(getattr(assignment.teacher, "staff_profile", None), "staff_id", assignment.teacher.username),
                "subject_workload": 0,
                "completed": 0,
                "published": 0,
            },
        )
        row["subject_workload"] += 1
        status = sheet_map.get((assignment.academic_class_id, assignment.subject_id))
        if status and status != ResultSheetStatus.DRAFT:
            row["completed"] += 1
        if status == ResultSheetStatus.PUBLISHED:
            row["published"] += 1
    for row in sorted(teacher_stats.values(), key=lambda item: (-item["completed"], item["staff_name"]))[:8]:
        workload = row["subject_workload"] or 1
        row["completion_rate"] = round((row["completed"] / workload) * 100, 2)
        teacher_upload_stats.append(row)

    alerts = []
    if weak_subjects:
        alerts.append(f"Weakest subject currently is {weak_subjects[0]['subject']} at {weak_subjects[0]['average_score']}%.")
    if fee_payment_rate < 70:
        alerts.append("Fee recovery rate is below 70%; finance follow-up is needed.")
    if exam_participation_rate < 80:
        alerts.append("CBT participation is below target and may affect assessment integrity.")
    if current_attendance < 75:
        alerts.append("School-wide attendance is below the 75% benchmark.")

    return {
        "available": True,
        "total_students": total_students,
        "total_staff": total_staff,
        "attendance": {
            "current": current_attendance,
            "delta": attendance_delta,
        },
        "top_performing_class": top_performing_class,
        "class_summary": class_summary,
        "weak_subjects": weak_subjects,
        "top_students": top_students,
        "teacher_upload_stats": teacher_upload_stats,
        "fee_payment_rate": fee_payment_rate,
        "exam_participation_rate": exam_participation_rate,
        "result_publication_rate": result_publication_rate,
        "alerts": alerts,
    }
