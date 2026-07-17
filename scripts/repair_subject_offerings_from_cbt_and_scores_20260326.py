from collections import defaultdict

from django.db import transaction

from apps.academics.models import StudentClassEnrollment, StudentSubjectEnrollment
from apps.cbt.models import CBTAttemptStatus, CBTWritebackTarget, ExamAttempt
from apps.results.models import StudentSubjectScore
from apps.setup_wizard.models import SystemSetupState


ATTEMPT_STATUSES = (
    CBTAttemptStatus.IN_PROGRESS,
    CBTAttemptStatus.SUBMITTED,
    CBTAttemptStatus.FINALIZED,
)


def _all_score_fields_zero(score):
    return all(
        [
            score.ca1 == 0,
            score.ca2 == 0,
            score.ca3 == 0,
            score.ca4 == 0,
            score.objective == 0,
            score.theory == 0,
        ]
    )


def main():
    setup = SystemSetupState.get_solo()
    session = setup.current_session
    term = setup.current_term
    if session is None or term is None:
        raise RuntimeError("Current session/term is not configured.")

    subject_enrollments = list(
        StudentSubjectEnrollment.objects.filter(session=session, is_active=True)
        .select_related("student", "subject")
        .order_by("student_id", "subject_id")
    )
    active_class_rows = {
        row.student_id: row.academic_class
        for row in StudentClassEnrollment.objects.filter(session=session, is_active=True).select_related(
            "academic_class"
        )
    }

    ca2_pairs = set(
        ExamAttempt.objects.filter(
            exam__session=session,
            exam__term=term,
            exam__blueprint__objective_writeback_target=CBTWritebackTarget.CA2,
            status__in=ATTEMPT_STATUSES,
        ).values_list("student_id", "exam__subject_id")
    )
    exam_pairs = set(
        ExamAttempt.objects.filter(
            exam__session=session,
            exam__term=term,
            exam__blueprint__objective_writeback_target=CBTWritebackTarget.OBJECTIVE,
            status__in=ATTEMPT_STATUSES,
        ).values_list("student_id", "exam__subject_id")
    )

    zero_only_score_pairs = set()
    for row in StudentSubjectScore.objects.filter(
        result_sheet__session=session,
        result_sheet__term=term,
    ).select_related("result_sheet"):
        if _all_score_fields_zero(row):
            zero_only_score_pairs.add((row.student_id, row.result_sheet.subject_id))

    target_enrollments = []
    by_class = defaultdict(int)
    for enrollment in subject_enrollments:
        pair = (enrollment.student_id, enrollment.subject_id)
        if pair in ca2_pairs or pair in exam_pairs:
            continue
        target_enrollments.append(enrollment)
        class_row = active_class_rows.get(enrollment.student_id)
        class_code = class_row.code if class_row else "UNKNOWN"
        by_class[class_code] += 1

    target_pairs = {(row.student_id, row.subject_id) for row in target_enrollments}
    target_scores = []
    for score in StudentSubjectScore.objects.filter(
        result_sheet__session=session,
        result_sheet__term=term,
    ).select_related("result_sheet"):
        if (score.student_id, score.result_sheet.subject_id) in target_pairs:
            target_scores.append(score)

    with transaction.atomic():
        for enrollment in target_enrollments:
            enrollment.is_active = False
            enrollment.save(update_fields=["is_active", "updated_at"])
        for score in target_scores:
            score.delete()

    print(
        {
            "session": session.name,
            "term": term.name,
            "subject_enrollments_scanned": len(subject_enrollments),
            "deactivated_subject_enrollments": len(target_enrollments),
            "deleted_current_term_score_rows": len(target_scores),
            "by_class": dict(sorted(by_class.items())),
        }
    )


main()
