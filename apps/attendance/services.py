from __future__ import annotations

from datetime import date

from django.db.utils import OperationalError, ProgrammingError

from apps.academics.models import FormTeacherAssignment, StudentClassEnrollment, Term
from apps.attendance.models import AttendanceRecord, AttendanceStatus, SchoolCalendar
from apps.setup_wizard.services import get_setup_state


def is_weekend(day: date):
    return day.weekday() >= 5


def compute_student_attendance_percentage(*, student, calendar: SchoolCalendar, academic_class):
    valid_school_days = calendar.school_days_count()
    if valid_school_days <= 0:
        return 0.0
    present_days = AttendanceRecord.objects.filter(
        calendar=calendar,
        academic_class=academic_class,
        student=student,
        status=AttendanceStatus.PRESENT,
    ).count()
    percentage = (present_days / valid_school_days) * 100
    return round(percentage, 2)


def get_current_student_attendance_snapshot(student):
    try:
        setup_state = get_setup_state()
    except (OperationalError, ProgrammingError):
        return None
    if not setup_state.current_session_id or not setup_state.current_term_id:
        return None
    return get_student_attendance_snapshot_for_window(
        student,
        session=setup_state.current_session,
        term=setup_state.current_term,
    )


def get_student_attendance_snapshot_for_window(student, *, session, term=None):
    if not session:
        return None

    enrollment = (
        StudentClassEnrollment.objects.select_related("academic_class")
        .filter(student=student, session=session, is_active=True)
        .first()
    )
    if not enrollment:
        return None

    if term is None:
        term = (
            Term.objects.filter(session=session)
            .order_by("created_at")
            .first()
        )
    if not term:
        return None

    calendar = SchoolCalendar.objects.filter(term=term).first()
    if not calendar:
        return None

    records_qs = AttendanceRecord.objects.filter(
        calendar=calendar,
        academic_class=enrollment.academic_class,
        student=student,
    )
    marked_days = records_qs.count()
    present_days = records_qs.filter(status=AttendanceStatus.PRESENT).count()
    absent_days = records_qs.filter(status=AttendanceStatus.ABSENT).count()

    valid_school_days = calendar.school_days_count()
    unmarked_days = max(valid_school_days - marked_days, 0)

    if valid_school_days <= 0:
        percentage = 0.0
    else:
        percentage = round((present_days / valid_school_days) * 100, 2)

    return {
        "percentage": percentage,
        "present_days": present_days,
        "absent_days": absent_days,
        "marked_days": marked_days,
        "unmarked_days": unmarked_days,
        "valid_school_days": valid_school_days,
        "calendar": calendar,
        "session": session,
        "term": term,
        "academic_class": enrollment.academic_class,
    }


def get_form_teacher_assignments_for_current_session(user):
    try:
        setup_state = get_setup_state()
    except (OperationalError, ProgrammingError):
        return FormTeacherAssignment.objects.none()
    qs = FormTeacherAssignment.objects.select_related("academic_class", "session").filter(
        teacher=user,
        is_active=True,
    )
    if setup_state.current_session_id:
        qs = qs.filter(session=setup_state.current_session)
    return qs.order_by("academic_class__code")
