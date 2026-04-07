from apps.accounts.constants import ROLE_FORM_TEACHER, ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_VP
from apps.academics.models import StudentClassEnrollment
from apps.attendance.models import AttendanceRecord, AttendanceStatus, SchoolCalendar
from apps.results.models import ClassResultStudentRecord
from apps.setup_wizard.services import get_setup_state
from django.contrib.auth import get_user_model


User = get_user_model()


def _actor():
    for role_code in (ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL, ROLE_FORM_TEACHER):
        row = (
            User.objects.filter(primary_role__code=role_code, is_active=True)
            .order_by("id")
            .first()
        )
        if row:
            return row
    return User.objects.filter(is_superuser=True, is_active=True).order_by("id").first()


setup_state = get_setup_state()
session = setup_state.current_session
term = setup_state.current_term
if session is None or term is None:
    raise RuntimeError("Current session/term is not configured.")

calendar = SchoolCalendar.objects.filter(term=term, session=session).first()
if calendar is None:
    raise RuntimeError("Current term school calendar is not configured.")

valid_days = list(calendar.school_days_between())
actor = _actor()
enrollments = list(
    StudentClassEnrollment.objects.filter(session=session, is_active=True)
    .select_related("student", "academic_class")
    .order_by("academic_class__code", "student__username")
)

created_count = 0
updated_count = 0
for enrollment in enrollments:
    record_class = enrollment.academic_class.instructional_class
    for school_day in valid_days:
        record, created = AttendanceRecord.objects.update_or_create(
            calendar=calendar,
            academic_class=record_class,
            student=enrollment.student,
            date=school_day,
            defaults={
                "status": AttendanceStatus.PRESENT,
                "marked_by": actor,
            },
        )
        if created:
            created_count += 1
        else:
            updated_count += 1

refreshed_records = 0
for record in (
    ClassResultStudentRecord.objects.filter(
        compilation__session=session,
        compilation__term=term,
    )
    .select_related("compilation", "student")
    .order_by("id")
):
    record.refresh_attendance(calendar, record.compilation.academic_class)
    record.save(update_fields=["attendance_percentage", "updated_at"])
    refreshed_records += 1

print("FULL_ATTENDANCE_APPLIED")
print("session", session.name)
print("term", term.get_name_display())
print("calendar_days", len(valid_days))
print("enrollments", len(enrollments))
print("created_records", created_count)
print("updated_records", updated_count)
print("refreshed_result_records", refreshed_records)
