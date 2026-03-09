from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.cbt.models import (
    CBTExamStatus,
    CBTSimulationWrapperStatus,
    Exam,
    ExamReviewAction,
    SimulationWrapper,
)


def _transition_exam(*, exam: Exam, to_status, actor, action, comment=""):
    from_status = exam.status
    if from_status == to_status:
        return exam
    exam.status = to_status
    exam.save(update_fields=["status", "updated_at"])
    ExamReviewAction.objects.create(
        exam=exam,
        actor=actor,
        from_status=from_status,
        to_status=to_status,
        action=action,
        comment=comment,
    )
    return exam


def submit_exam_to_dean(*, exam: Exam, actor, comment=""):
    if exam.status != CBTExamStatus.DRAFT:
        raise ValidationError("Only draft exams can be submitted to Dean.")
    has_questions = exam.exam_questions.exists()
    has_simulations = exam.exam_simulations.exists()
    if not has_questions and not has_simulations:
        raise ValidationError(
            "Attach at least one question or simulation before submitting to Dean."
        )
    return _transition_exam(
        exam=exam,
        to_status=CBTExamStatus.PENDING_DEAN,
        actor=actor,
        action="SUBMIT_TO_DEAN",
        comment=comment,
    )


def submit_exam_to_it_manager(*, exam: Exam, actor, comment=""):
    if exam.status != CBTExamStatus.DRAFT:
        raise ValidationError("Only draft exams can be submitted to IT Manager.")
    if not exam.is_free_test:
        raise ValidationError("Only Free Test CBT can be submitted directly to IT Manager.")
    if not exam.exam_questions.exists():
        raise ValidationError("Attach at least one question before submitting to IT Manager.")
    return _transition_exam(
        exam=exam,
        to_status=CBTExamStatus.PENDING_IT,
        actor=actor,
        action="SUBMIT_TO_IT",
        comment=comment,
    )


def dean_approve_exam(*, exam: Exam, actor, comment=""):
    if exam.status != CBTExamStatus.PENDING_DEAN:
        raise ValidationError("Only pending exams can be approved.")
    exam.dean_reviewed_by = actor
    exam.dean_reviewed_at = timezone.now()
    exam.dean_review_comment = comment
    exam.save(
        update_fields=[
            "dean_reviewed_by",
            "dean_reviewed_at",
            "dean_review_comment",
            "updated_at",
        ]
    )
    return _transition_exam(
        exam=exam,
        to_status=CBTExamStatus.APPROVED,
        actor=actor,
        action="DEAN_APPROVE",
        comment=comment,
    )


def dean_reject_exam(*, exam: Exam, actor, comment):
    if exam.status != CBTExamStatus.PENDING_DEAN:
        raise ValidationError("Only pending exams can be rejected.")
    if not (comment or "").strip():
        raise ValidationError("Rejection comment is required.")
    exam.dean_reviewed_by = actor
    exam.dean_reviewed_at = timezone.now()
    exam.dean_review_comment = comment.strip()
    exam.save(
        update_fields=[
            "dean_reviewed_by",
            "dean_reviewed_at",
            "dean_review_comment",
            "updated_at",
        ]
    )
    return _transition_exam(
        exam=exam,
        to_status=CBTExamStatus.DRAFT,
        actor=actor,
        action="DEAN_REJECT",
        comment=comment,
    )


def it_activate_exam(
    *,
    exam: Exam,
    actor,
    open_now,
    is_time_based,
    schedule_start,
    schedule_end,
    comment="",
):
    allowed_statuses = {CBTExamStatus.APPROVED}
    if exam.is_free_test:
        allowed_statuses.add(CBTExamStatus.PENDING_IT)
    if exam.status not in allowed_statuses:
        if exam.is_free_test:
            raise ValidationError("Only Free Test pending-IT exams can be activated.")
        raise ValidationError("Only Dean-approved exams can be activated.")
    from_status = exam.status
    exam.open_now = open_now
    exam.is_time_based = is_time_based
    exam.schedule_start = schedule_start
    exam.schedule_end = schedule_end
    exam.activated_by = actor
    exam.activated_at = timezone.now()
    exam.activation_comment = (comment or "").strip()
    exam.status = CBTExamStatus.ACTIVE
    exam.full_clean()
    exam.save(
        update_fields=[
            "open_now",
            "is_time_based",
            "schedule_start",
            "schedule_end",
            "activated_by",
            "activated_at",
            "activation_comment",
            "status",
            "updated_at",
        ]
    )
    ExamReviewAction.objects.create(
        exam=exam,
        actor=actor,
        from_status=from_status,
        to_status=CBTExamStatus.ACTIVE,
        action="IT_ACTIVATE",
        comment=comment or "",
    )
    return exam


def it_close_exam(*, exam: Exam, actor, comment=""):
    if exam.status != CBTExamStatus.ACTIVE:
        raise ValidationError("Only active exams can be closed.")
    return _transition_exam(
        exam=exam,
        to_status=CBTExamStatus.CLOSED,
        actor=actor,
        action="IT_CLOSE",
        comment=comment or "",
    )


def submit_simulation_to_dean(*, wrapper: SimulationWrapper, actor, comment=""):
    if wrapper.status not in {
        CBTSimulationWrapperStatus.DRAFT,
        CBTSimulationWrapperStatus.REJECTED,
    }:
        raise ValidationError("Only draft/rejected simulations can be submitted to Dean.")
    wrapper.status = CBTSimulationWrapperStatus.PENDING_DEAN
    wrapper.dean_review_comment = (comment or "").strip()
    wrapper.save(update_fields=["status", "dean_review_comment", "updated_at"])
    return wrapper


def dean_approve_simulation(*, wrapper: SimulationWrapper, actor, comment=""):
    if wrapper.status != CBTSimulationWrapperStatus.PENDING_DEAN:
        raise ValidationError("Only pending simulations can be approved.")
    wrapper.status = CBTSimulationWrapperStatus.APPROVED
    wrapper.dean_reviewed_by = actor
    wrapper.dean_reviewed_at = timezone.now()
    wrapper.dean_review_comment = (comment or "").strip()
    wrapper.save(
        update_fields=[
            "status",
            "dean_reviewed_by",
            "dean_reviewed_at",
            "dean_review_comment",
            "updated_at",
        ]
    )
    return wrapper


def dean_reject_simulation(*, wrapper: SimulationWrapper, actor, comment):
    if wrapper.status != CBTSimulationWrapperStatus.PENDING_DEAN:
        raise ValidationError("Only pending simulations can be rejected.")
    if not (comment or "").strip():
        raise ValidationError("Rejection comment is required.")
    wrapper.status = CBTSimulationWrapperStatus.REJECTED
    wrapper.dean_reviewed_by = actor
    wrapper.dean_reviewed_at = timezone.now()
    wrapper.dean_review_comment = comment.strip()
    wrapper.save(
        update_fields=[
            "status",
            "dean_reviewed_by",
            "dean_reviewed_at",
            "dean_review_comment",
            "updated_at",
        ]
    )
    return wrapper
