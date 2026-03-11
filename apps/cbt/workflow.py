import hashlib
import json

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.cbt.models import (
    CBTExamStatus,
    CBTSimulationWrapperStatus,
    Exam,
    ExamReviewAction,
    SimulationWrapper,
)


def _file_name(file_field):
    if not file_field:
        return ""
    return getattr(file_field, "name", "") or ""


def _activation_snapshot_payload(exam: Exam):
    blueprint = getattr(exam, "blueprint", None)
    exam_questions = exam.exam_questions.select_related("question").prefetch_related(
        "question__options",
        "question__correct_answer__correct_options",
    ).order_by("sort_order")
    exam_simulations = exam.exam_simulations.select_related("simulation_wrapper").order_by("sort_order")
    return {
        "exam": {
            "id": exam.id,
            "title": exam.title,
            "description": exam.description,
            "exam_type": exam.exam_type,
            "status": exam.status,
            "created_by_id": exam.created_by_id,
            "assignment_id": exam.assignment_id,
            "subject_id": exam.subject_id,
            "academic_class_id": exam.academic_class_id,
            "session_id": exam.session_id,
            "term_id": exam.term_id,
            "question_bank_id": exam.question_bank_id,
            "dean_reviewed_by_id": exam.dean_reviewed_by_id,
            "dean_reviewed_at": exam.dean_reviewed_at.isoformat() if exam.dean_reviewed_at else "",
            "activated_by_id": exam.activated_by_id,
            "activated_at": exam.activated_at.isoformat() if exam.activated_at else "",
            "activation_comment": exam.activation_comment,
            "schedule_start": exam.schedule_start.isoformat() if exam.schedule_start else "",
            "schedule_end": exam.schedule_end.isoformat() if exam.schedule_end else "",
            "is_time_based": bool(exam.is_time_based),
            "open_now": bool(exam.open_now),
            "is_free_test": bool(exam.is_free_test),
        },
        "blueprint": {
            "duration_minutes": getattr(blueprint, "duration_minutes", None),
            "max_attempts": getattr(blueprint, "max_attempts", None),
            "shuffle_questions": bool(getattr(blueprint, "shuffle_questions", False)),
            "shuffle_options": bool(getattr(blueprint, "shuffle_options", False)),
            "instructions": getattr(blueprint, "instructions", ""),
            "section_config": getattr(blueprint, "section_config", {}) or {},
            "passing_score": str(getattr(blueprint, "passing_score", "0")),
            "objective_writeback_target": getattr(blueprint, "objective_writeback_target", ""),
            "theory_enabled": bool(getattr(blueprint, "theory_enabled", False)),
            "theory_writeback_target": getattr(blueprint, "theory_writeback_target", ""),
            "auto_show_result_on_submit": bool(getattr(blueprint, "auto_show_result_on_submit", False)),
            "finalize_on_logout": bool(getattr(blueprint, "finalize_on_logout", False)),
            "allow_retake": bool(getattr(blueprint, "allow_retake", False)),
        },
        "questions": [
            {
                "exam_question_id": row.id,
                "sort_order": row.sort_order,
                "marks": str(row.marks),
                "question": {
                    "id": row.question_id,
                    "question_type": row.question.question_type,
                    "stem": row.question.stem,
                    "rich_stem": row.question.rich_stem,
                    "topic": row.question.topic,
                    "difficulty": row.question.difficulty,
                    "marks": str(row.question.marks),
                    "source_type": row.question.source_type,
                    "source_reference": row.question.source_reference,
                    "stimulus_image": _file_name(row.question.stimulus_image),
                    "stimulus_video": _file_name(row.question.stimulus_video),
                    "stimulus_caption": row.question.stimulus_caption,
                    "shared_stimulus_key": row.question.shared_stimulus_key,
                    "options": [
                        {
                            "id": option.id,
                            "label": option.label,
                            "option_text": option.option_text,
                            "sort_order": option.sort_order,
                        }
                        for option in row.question.options.order_by("sort_order", "id")
                    ],
                    "correct_answers": (
                        [
                            {
                                "id": row.question.correct_answer.id,
                                "note": row.question.correct_answer.note,
                                "is_finalized": bool(row.question.correct_answer.is_finalized),
                                "correct_option_ids": list(
                                    row.question.correct_answer.correct_options.order_by("sort_order", "id").values_list("id", flat=True)
                                ),
                            }
                        ]
                        if getattr(row.question, "correct_answer", None)
                        else []
                    ),
                },
            }
            for row in exam_questions
        ],
        "simulations": [
            {
                "exam_simulation_id": row.id,
                "sort_order": row.sort_order,
                "writeback_target": row.writeback_target,
                "max_score_override": str(row.max_score_override) if row.max_score_override is not None else "",
                "is_required": bool(row.is_required),
                "wrapper": {
                    "id": row.simulation_wrapper_id,
                    "tool_name": row.simulation_wrapper.tool_name,
                    "tool_type": row.simulation_wrapper.tool_type,
                    "source_provider": row.simulation_wrapper.source_provider,
                    "source_reference_url": row.simulation_wrapper.source_reference_url,
                    "tool_category": row.simulation_wrapper.tool_category,
                    "description": row.simulation_wrapper.description,
                    "online_url": row.simulation_wrapper.online_url,
                    "offline_asset_path": row.simulation_wrapper.offline_asset_path,
                    "score_mode": row.simulation_wrapper.score_mode,
                    "max_score": str(row.simulation_wrapper.max_score),
                    "scoring_callback_type": row.simulation_wrapper.scoring_callback_type,
                    "evidence_required": bool(row.simulation_wrapper.evidence_required),
                },
            }
            for row in exam_simulations
        ],
    }


def _activation_snapshot_hash(snapshot):
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    if exam.activation_snapshot_hash:
        raise ValidationError("Exam activation snapshot already exists for this exam.")
    exam.activation_snapshot = _activation_snapshot_payload(exam)
    exam.activation_snapshot_hash = _activation_snapshot_hash(exam.activation_snapshot)
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
            "activation_snapshot",
            "activation_snapshot_hash",
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
