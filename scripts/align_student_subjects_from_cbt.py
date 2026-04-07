import os

from apps.accounts.models import StudentProfile
from apps.academics.models import StudentSubjectEnrollment
from apps.cbt.models import CBTAttemptStatus, CBTExamType, ExamAttempt
from apps.setup_wizard.services import get_setup_state


student_number = (os.getenv("STUDENT_NUMBER") or "NDGAK/20/177").strip()
forced_subject_codes = [
    code.strip().upper()
    for code in (os.getenv("SUBJECT_CODES") or "").split(",")
    if code.strip()
]
setup_state = get_setup_state()
session = setup_state.current_session

if session is None:
    raise RuntimeError("Current academic session is not configured.")

profile = StudentProfile.objects.select_related("user").get(student_number=student_number)
student = profile.user

attempts = []
subject_ids = []
seen_subject_ids = set()
if forced_subject_codes:
    code_map = {
        enrollment.subject.code.upper(): enrollment.subject_id
        for enrollment in StudentSubjectEnrollment.objects.filter(student=student, session=session).select_related("subject")
    }
    missing_codes = [code for code in forced_subject_codes if code not in code_map]
    if missing_codes:
        raise RuntimeError(
            f"Forced subject codes not found in {student_number} session enrollments: {', '.join(missing_codes)}"
        )
    for code in forced_subject_codes:
        subject_id = code_map[code]
        if subject_id not in seen_subject_ids:
            seen_subject_ids.add(subject_id)
            subject_ids.append(subject_id)
else:
    attempts = list(
        ExamAttempt.objects.filter(
            student=student,
            exam__session=session,
            exam__exam_type=CBTExamType.EXAM,
            status__in=[CBTAttemptStatus.SUBMITTED, CBTAttemptStatus.FINALIZED],
        )
        .select_related("exam", "exam__subject")
        .order_by("exam__schedule_start", "exam__title", "attempt_number")
    )

    for attempt in attempts:
        subject_id = attempt.exam.subject_id
        if not subject_id or subject_id in seen_subject_ids:
            continue
        seen_subject_ids.add(subject_id)
        subject_ids.append(subject_id)

    if not subject_ids:
        raise RuntimeError(f"No submitted/finalized EXAM CBT attempts found for {student_number} in {session.name}.")

enrollments = list(
    StudentSubjectEnrollment.objects.filter(student=student, session=session).select_related("subject")
)

for subject_id in subject_ids:
    StudentSubjectEnrollment.objects.update_or_create(
        student=student,
        subject_id=subject_id,
        session=session,
        defaults={"is_active": True},
    )

updated = 0
for enrollment in enrollments:
    should_be_active = enrollment.subject_id in seen_subject_ids
    if enrollment.is_active != should_be_active:
        enrollment.is_active = should_be_active
        enrollment.save(update_fields=["is_active", "updated_at"])
        updated += 1

active_subjects = list(
    StudentSubjectEnrollment.objects.filter(student=student, session=session, is_active=True)
    .select_related("subject")
    .order_by("subject__name")
)

print("CBT_SUBJECT_ALIGNMENT_COMPLETE")
print("student", student_number)
print("session", session.name)
print("exam_attempts", len(attempts))
print("forced_subject_codes", ",".join(forced_subject_codes) if forced_subject_codes else "-")
print("active_subject_count", len(active_subjects))
print("updated_enrollments", updated)
for enrollment in active_subjects:
    print(enrollment.subject.code, "|", enrollment.subject.name)
