from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from threading import local
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.sync.models import (
    SyncContentChange,
    SyncContentObjectType,
    SyncContentOperation,
    SyncContentStream,
    SyncPullCursor,
)
from apps.sync.policies import lan_results_only_mode_enabled
from apps.sync.services import queue_cbt_content_change_sync

_THREAD_LOCAL = local()
logger = logging.getLogger(__name__)


class SyncDependencyUnavailable(RuntimeError):
    pass


def _decimal(value, *, fallback="0"):
    candidate = value
    if candidate in (None, ""):
        candidate = fallback
    try:
        return Decimal(str(candidate))
    except (InvalidOperation, ValueError):
        return Decimal(str(fallback))


def _dt(value):
    raw = (value or "").strip() if isinstance(value, str) else ""
    if not raw:
        return None
    parsed = parse_datetime(raw.replace("Z", "+00:00"))
    return parsed


def _dt_iso(value):
    if not value:
        return ""
    return value.isoformat()


def _file_name(file_field):
    if not file_field:
        return ""
    return getattr(file_field, "name", "") or ""


def _as_int(value, *, fallback=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def is_cbt_change_capture_suppressed():
    return bool(getattr(_THREAD_LOCAL, "suppress_cbt_change_capture", False))


@contextmanager
def suppress_cbt_change_capture():
    previous = bool(getattr(_THREAD_LOCAL, "suppress_cbt_change_capture", False))
    _THREAD_LOCAL.suppress_cbt_change_capture = True
    try:
        yield
    finally:
        _THREAD_LOCAL.suppress_cbt_change_capture = previous


def _serialize_cbt_instance(instance):
    from apps.cbt.models import (
        CorrectAnswer,
        Exam,
        ExamBlueprint,
        ExamQuestion,
        ExamSimulation,
        Option,
        Question,
        QuestionBank,
        SimulationWrapper,
    )

    if isinstance(instance, QuestionBank):
        return SyncContentObjectType.QUESTION_BANK, {
            "id": instance.id,
            "name": instance.name,
            "description": instance.description,
            "owner_id": instance.owner_id,
            "assignment_id": instance.assignment_id,
            "subject_id": instance.subject_id,
            "academic_class_id": instance.academic_class_id,
            "session_id": instance.session_id,
            "term_id": instance.term_id,
            "is_active": bool(instance.is_active),
            "updated_at": _dt_iso(instance.updated_at),
        }
    if isinstance(instance, Question):
        return SyncContentObjectType.QUESTION, {
            "id": instance.id,
            "question_bank_id": instance.question_bank_id,
            "created_by_id": instance.created_by_id,
            "subject_id": instance.subject_id,
            "question_type": instance.question_type,
            "stem": instance.stem,
            "topic": instance.topic,
            "difficulty": instance.difficulty,
            "marks": str(instance.marks),
            "source_type": instance.source_type,
            "source_reference": instance.source_reference,
            "rich_stem": instance.rich_stem,
            "stimulus_image": _file_name(instance.stimulus_image),
            "stimulus_video": _file_name(instance.stimulus_video),
            "stimulus_caption": instance.stimulus_caption,
            "shared_stimulus_key": instance.shared_stimulus_key,
            "dean_comment": instance.dean_comment,
            "is_active": bool(instance.is_active),
            "updated_at": _dt_iso(instance.updated_at),
        }
    if isinstance(instance, Option):
        return SyncContentObjectType.OPTION, {
            "id": instance.id,
            "question_id": instance.question_id,
            "label": instance.label,
            "option_text": instance.option_text,
            "sort_order": instance.sort_order,
            "updated_at": _dt_iso(instance.updated_at),
        }
    if isinstance(instance, CorrectAnswer):
        return SyncContentObjectType.CORRECT_ANSWER, {
            "id": instance.id,
            "question_id": instance.question_id,
            "note": instance.note,
            "is_finalized": bool(instance.is_finalized),
            "correct_option_ids": list(
                instance.correct_options.order_by("id").values_list("id", flat=True)
            ),
            "updated_at": _dt_iso(instance.updated_at),
        }
    if isinstance(instance, Exam):
        return SyncContentObjectType.EXAM, {
            "id": instance.id,
            "title": instance.title,
            "description": instance.description,
            "exam_type": instance.exam_type,
            "status": instance.status,
            "created_by_id": instance.created_by_id,
            "assignment_id": instance.assignment_id,
            "subject_id": instance.subject_id,
            "academic_class_id": instance.academic_class_id,
            "session_id": instance.session_id,
            "term_id": instance.term_id,
            "question_bank_id": instance.question_bank_id,
            "dean_reviewed_by_id": instance.dean_reviewed_by_id,
            "dean_reviewed_at": _dt_iso(instance.dean_reviewed_at),
            "dean_review_comment": instance.dean_review_comment,
            "activated_by_id": instance.activated_by_id,
            "activated_at": _dt_iso(instance.activated_at),
            "activation_comment": instance.activation_comment,
            "schedule_start": _dt_iso(instance.schedule_start),
            "schedule_end": _dt_iso(instance.schedule_end),
            "is_time_based": bool(instance.is_time_based),
            "open_now": bool(instance.open_now),
            "is_free_test": bool(instance.is_free_test),
            "updated_at": _dt_iso(instance.updated_at),
        }
    if isinstance(instance, ExamBlueprint):
        return SyncContentObjectType.EXAM_BLUEPRINT, {
            "id": instance.id,
            "exam_id": instance.exam_id,
            "duration_minutes": instance.duration_minutes,
            "max_attempts": instance.max_attempts,
            "shuffle_questions": bool(instance.shuffle_questions),
            "shuffle_options": bool(instance.shuffle_options),
            "instructions": instance.instructions,
            "section_config": instance.section_config or [],
            "passing_score": str(instance.passing_score),
            "objective_writeback_target": instance.objective_writeback_target,
            "theory_enabled": bool(instance.theory_enabled),
            "theory_writeback_target": instance.theory_writeback_target,
            "auto_show_result_on_submit": bool(instance.auto_show_result_on_submit),
            "finalize_on_logout": bool(instance.finalize_on_logout),
            "allow_retake": bool(instance.allow_retake),
            "updated_at": _dt_iso(instance.updated_at),
        }
    if isinstance(instance, ExamQuestion):
        return SyncContentObjectType.EXAM_QUESTION, {
            "id": instance.id,
            "exam_id": instance.exam_id,
            "question_id": instance.question_id,
            "sort_order": instance.sort_order,
            "marks": str(instance.marks),
            "updated_at": _dt_iso(instance.updated_at),
        }
    if isinstance(instance, SimulationWrapper):
        return SyncContentObjectType.SIMULATION_WRAPPER, {
            "id": instance.id,
            "tool_name": instance.tool_name,
            "tool_type": instance.tool_type,
            "source_provider": instance.source_provider,
            "source_reference_url": instance.source_reference_url,
            "tool_category": instance.tool_category,
            "description": instance.description,
            "online_url": instance.online_url,
            "offline_asset_path": instance.offline_asset_path,
            "score_mode": instance.score_mode,
            "max_score": str(instance.max_score),
            "scoring_callback_type": instance.scoring_callback_type,
            "evidence_required": bool(instance.evidence_required),
            "status": instance.status,
            "created_by_id": instance.created_by_id,
            "dean_reviewed_by_id": instance.dean_reviewed_by_id,
            "dean_reviewed_at": _dt_iso(instance.dean_reviewed_at),
            "dean_review_comment": instance.dean_review_comment,
            "is_active": bool(instance.is_active),
            "updated_at": _dt_iso(instance.updated_at),
        }
    if isinstance(instance, ExamSimulation):
        return SyncContentObjectType.EXAM_SIMULATION, {
            "id": instance.id,
            "exam_id": instance.exam_id,
            "simulation_wrapper_id": instance.simulation_wrapper_id,
            "sort_order": instance.sort_order,
            "writeback_target": instance.writeback_target,
            "max_score_override": (
                str(instance.max_score_override) if instance.max_score_override is not None else ""
            ),
            "is_required": bool(instance.is_required),
            "updated_at": _dt_iso(instance.updated_at),
        }
    return None, {}


def register_cbt_content_change(*, instance, operation=SyncContentOperation.UPSERT):
    if is_cbt_change_capture_suppressed():
        return None
    object_type, payload = _serialize_cbt_instance(instance)
    if not object_type:
        return None
    payload_value = payload if operation == SyncContentOperation.UPSERT else {}
    try:
        change = SyncContentChange.objects.create(
            stream=SyncContentStream.CBT_CONTENT,
            object_type=object_type,
            operation=operation,
            object_pk=str(instance.pk),
            payload=payload_value,
            source_node_id=(getattr(settings, "SYNC_LOCAL_NODE_ID", "") or "")[:80],
        )
        try:
            queue_cbt_content_change_sync(change=change)
        except Exception as exc:
            logger.warning("Skipped CBT outbox queue capture: %s", exc)
        return change
    except (ProgrammingError, OperationalError) as exc:
        # Allow core workflows to continue when sync schema is not migrated yet.
        logger.warning(
            "Skipped SyncContentChange write because sync schema is unavailable: %s",
            exc,
        )
        return None


def build_cbt_content_feed(*, after_id=0, limit=200):
    if lan_results_only_mode_enabled():
        return {
            "stream": SyncContentStream.CBT_CONTENT,
            "after_id": max(_as_int(after_id, fallback=0), 0),
            "next_after_id": max(_as_int(after_id, fallback=0), 0),
            "has_more": False,
            "count": 0,
            "generated_at": timezone.now().isoformat(),
            "changes": [],
        }
    safe_after_id = max(_as_int(after_id, fallback=0), 0)
    safe_limit = max(min(_as_int(limit, fallback=200), 500), 1)
    rows = list(
        SyncContentChange.objects.filter(
            stream=SyncContentStream.CBT_CONTENT,
            id__gt=safe_after_id,
        )
        .order_by("id")[:safe_limit]
    )
    if rows:
        next_after_id = rows[-1].id
    else:
        next_after_id = safe_after_id
    has_more = SyncContentChange.objects.filter(
        stream=SyncContentStream.CBT_CONTENT,
        id__gt=next_after_id,
    ).exists()
    changes = [
        {
            "id": row.id,
            "stream": row.stream,
            "object_type": row.object_type,
            "operation": row.operation,
            "object_pk": row.object_pk,
            "payload": row.payload or {},
            "created_at": _dt_iso(row.created_at),
        }
        for row in rows
    ]
    return {
        "stream": SyncContentStream.CBT_CONTENT,
        "after_id": safe_after_id,
        "next_after_id": next_after_id,
        "has_more": has_more,
        "count": len(changes),
        "generated_at": _dt_iso(timezone.now()),
        "changes": changes,
    }


def _set_updated_at(model_class, pk, value):
    parsed = _dt(value)
    if parsed is None:
        return
    model_class.objects.filter(pk=pk).update(updated_at=parsed)


def _update_or_insert_by_pk(model_class, obj_id, defaults):
    updated = model_class.objects.filter(pk=obj_id).update(**defaults)
    if updated:
        return model_class.objects.get(pk=obj_id), False
    instance = model_class(id=obj_id, **defaults)
    model_class.objects.bulk_create([instance])
    return model_class.objects.get(pk=obj_id), True


def _apply_upsert(change):
    from apps.cbt.models import (
        CorrectAnswer,
        Exam,
        ExamBlueprint,
        ExamQuestion,
        ExamSimulation,
        Option,
        Question,
        QuestionBank,
        SimulationWrapper,
    )

    object_type = change.get("object_type")
    payload = change.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("Invalid payload format.")

    def _resolved_question_bank_id(raw_value):
        bank_id = _as_int(raw_value, fallback=0)
        if bank_id <= 0:
            return None
        if QuestionBank.objects.filter(pk=bank_id).exists():
            return bank_id
        return None

    try:
        if object_type == SyncContentObjectType.QUESTION_BANK:
            obj_id = _as_int(payload.get("id"))
            defaults = {
                "name": payload.get("name", ""),
                "description": payload.get("description", ""),
                "owner_id": payload.get("owner_id"),
                "assignment_id": payload.get("assignment_id"),
                "subject_id": payload.get("subject_id"),
                "academic_class_id": payload.get("academic_class_id"),
                "session_id": payload.get("session_id"),
                "term_id": payload.get("term_id"),
                "is_active": bool(payload.get("is_active", True)),
            }
            QuestionBank.objects.filter(
                owner_id=defaults["owner_id"],
                name=defaults["name"],
                subject_id=defaults["subject_id"],
                academic_class_id=defaults["academic_class_id"],
                session_id=defaults["session_id"],
                term_id=defaults["term_id"],
            ).exclude(pk=obj_id).delete()
            obj, _ = _update_or_insert_by_pk(
                QuestionBank,
                obj_id,
                defaults,
            )
            _set_updated_at(QuestionBank, obj.pk, payload.get("updated_at"))
            return
        if object_type == SyncContentObjectType.QUESTION:
            obj_id = _as_int(payload.get("id"))
            obj, _ = _update_or_insert_by_pk(
                Question,
                obj_id,
                {
                    "question_bank_id": _resolved_question_bank_id(payload.get("question_bank_id")),
                    "created_by_id": payload.get("created_by_id"),
                    "subject_id": payload.get("subject_id"),
                    "question_type": payload.get("question_type"),
                    "stem": payload.get("stem", ""),
                    "topic": payload.get("topic", ""),
                    "difficulty": payload.get("difficulty"),
                    "marks": _decimal(payload.get("marks"), fallback="1"),
                    "source_type": payload.get("source_type", Question.SourceType.MANUAL),
                    "source_reference": payload.get("source_reference", ""),
                    "rich_stem": payload.get("rich_stem", ""),
                    "stimulus_image": payload.get("stimulus_image", ""),
                    "stimulus_video": payload.get("stimulus_video", ""),
                    "stimulus_caption": payload.get("stimulus_caption", ""),
                    "shared_stimulus_key": payload.get("shared_stimulus_key", ""),
                    "dean_comment": payload.get("dean_comment", ""),
                    "is_active": bool(payload.get("is_active", True)),
                },
            )
            _set_updated_at(Question, obj.pk, payload.get("updated_at"))
            return
        if object_type == SyncContentObjectType.OPTION:
            obj_id = _as_int(payload.get("id"))
            question_id = payload.get("question_id")
            label = payload.get("label", Option.Label.A)
            Option.objects.filter(
                question_id=question_id,
                label=label,
            ).exclude(pk=obj_id).delete()
            obj, _ = _update_or_insert_by_pk(
                Option,
                obj_id,
                {
                    "question_id": question_id,
                    "label": label,
                    "option_text": payload.get("option_text", ""),
                    "sort_order": _as_int(payload.get("sort_order"), fallback=1),
                },
            )
            _set_updated_at(Option, obj.pk, payload.get("updated_at"))
            return
        if object_type == SyncContentObjectType.CORRECT_ANSWER:
            obj_id = _as_int(payload.get("id"))
            question_id = payload.get("question_id")
            CorrectAnswer.objects.filter(question_id=question_id).exclude(pk=obj_id).delete()
            answer, _ = CorrectAnswer.objects.update_or_create(
                pk=obj_id,
                defaults={
                    "question_id": question_id,
                    "note": payload.get("note", ""),
                    "is_finalized": bool(payload.get("is_finalized", False)),
                },
            )
            option_ids = payload.get("correct_option_ids") or []
            if isinstance(option_ids, list):
                answer.correct_options.set([_as_int(row) for row in option_ids])
            _set_updated_at(CorrectAnswer, answer.pk, payload.get("updated_at"))
            return
        if object_type == SyncContentObjectType.EXAM:
            obj_id = _as_int(payload.get("id"))
            obj, _ = Exam.objects.update_or_create(
                pk=obj_id,
                defaults={
                    "title": payload.get("title", ""),
                    "description": payload.get("description", ""),
                    "exam_type": payload.get("exam_type"),
                    "status": payload.get("status"),
                    "created_by_id": payload.get("created_by_id"),
                    "assignment_id": payload.get("assignment_id"),
                    "subject_id": payload.get("subject_id"),
                    "academic_class_id": payload.get("academic_class_id"),
                    "session_id": payload.get("session_id"),
                    "term_id": payload.get("term_id"),
                    "question_bank_id": _resolved_question_bank_id(payload.get("question_bank_id")),
                    "dean_reviewed_by_id": payload.get("dean_reviewed_by_id"),
                    "dean_reviewed_at": _dt(payload.get("dean_reviewed_at")),
                    "dean_review_comment": payload.get("dean_review_comment", ""),
                    "activated_by_id": payload.get("activated_by_id"),
                    "activated_at": _dt(payload.get("activated_at")),
                    "activation_comment": payload.get("activation_comment", ""),
                    "schedule_start": _dt(payload.get("schedule_start")),
                    "schedule_end": _dt(payload.get("schedule_end")),
                    "is_time_based": bool(payload.get("is_time_based", True)),
                    "open_now": bool(payload.get("open_now", False)),
                    "is_free_test": bool(payload.get("is_free_test", False)),
                },
            )
            _set_updated_at(Exam, obj.pk, payload.get("updated_at"))
            return
        if object_type == SyncContentObjectType.EXAM_BLUEPRINT:
            obj_id = _as_int(payload.get("id"))
            target_exam_id = payload.get("exam_id")
            defaults = {
                "exam_id": target_exam_id,
                "duration_minutes": _as_int(payload.get("duration_minutes"), fallback=60),
                "max_attempts": _as_int(payload.get("max_attempts"), fallback=1),
                "shuffle_questions": bool(payload.get("shuffle_questions", True)),
                "shuffle_options": bool(payload.get("shuffle_options", True)),
                "instructions": payload.get("instructions", ""),
                "section_config": payload.get("section_config") or [],
                "passing_score": _decimal(payload.get("passing_score"), fallback="0"),
                "objective_writeback_target": payload.get("objective_writeback_target"),
                "theory_enabled": bool(payload.get("theory_enabled", False)),
                "theory_writeback_target": payload.get("theory_writeback_target"),
                "auto_show_result_on_submit": bool(payload.get("auto_show_result_on_submit", True)),
                "finalize_on_logout": bool(payload.get("finalize_on_logout", True)),
                "allow_retake": bool(payload.get("allow_retake", False)),
            }
            obj = ExamBlueprint.objects.filter(exam_id=target_exam_id).first()
            if obj is None:
                obj = ExamBlueprint.objects.filter(pk=obj_id).first()
            if obj is not None:
                ExamBlueprint.objects.filter(pk=obj.pk).update(**defaults)
                obj.refresh_from_db()
            else:
                obj, _ = _update_or_insert_by_pk(ExamBlueprint, obj_id, defaults)
            _set_updated_at(ExamBlueprint, obj.pk, payload.get("updated_at"))
            return
        if object_type == SyncContentObjectType.EXAM_QUESTION:
            obj_id = _as_int(payload.get("id"))
            exam_id = payload.get("exam_id")
            question_id = payload.get("question_id")
            sort_order = _as_int(payload.get("sort_order"), fallback=1)
            ExamQuestion.objects.filter(exam_id=exam_id, question_id=question_id).exclude(pk=obj_id).delete()
            ExamQuestion.objects.filter(exam_id=exam_id, sort_order=sort_order).exclude(pk=obj_id).delete()
            obj, _ = _update_or_insert_by_pk(
                ExamQuestion,
                obj_id,
                {
                    "exam_id": exam_id,
                    "question_id": question_id,
                    "sort_order": sort_order,
                    "marks": _decimal(payload.get("marks"), fallback="1"),
                },
            )
            _set_updated_at(ExamQuestion, obj.pk, payload.get("updated_at"))
            return
        if object_type == SyncContentObjectType.SIMULATION_WRAPPER:
            obj_id = _as_int(payload.get("id"))
            obj, _ = SimulationWrapper.objects.update_or_create(
                pk=obj_id,
                defaults={
                    "tool_name": payload.get("tool_name", ""),
                    "tool_type": payload.get("tool_type", ""),
                    "source_provider": payload.get("source_provider"),
                    "source_reference_url": payload.get("source_reference_url", ""),
                    "tool_category": payload.get("tool_category"),
                    "description": payload.get("description", ""),
                    "online_url": payload.get("online_url", ""),
                    "offline_asset_path": payload.get("offline_asset_path", ""),
                    "score_mode": payload.get("score_mode"),
                    "max_score": _decimal(payload.get("max_score"), fallback="10"),
                    "scoring_callback_type": payload.get("scoring_callback_type"),
                    "evidence_required": bool(payload.get("evidence_required", False)),
                    "status": payload.get("status"),
                    "created_by_id": payload.get("created_by_id"),
                    "dean_reviewed_by_id": payload.get("dean_reviewed_by_id"),
                    "dean_reviewed_at": _dt(payload.get("dean_reviewed_at")),
                    "dean_review_comment": payload.get("dean_review_comment", ""),
                    "is_active": bool(payload.get("is_active", True)),
                },
            )
            _set_updated_at(SimulationWrapper, obj.pk, payload.get("updated_at"))
            return
        if object_type == SyncContentObjectType.EXAM_SIMULATION:
            obj_id = _as_int(payload.get("id"))
            max_score_override = payload.get("max_score_override")
            obj, _ = ExamSimulation.objects.update_or_create(
                pk=obj_id,
                defaults={
                    "exam_id": payload.get("exam_id"),
                    "simulation_wrapper_id": payload.get("simulation_wrapper_id"),
                    "sort_order": _as_int(payload.get("sort_order"), fallback=1),
                    "writeback_target": payload.get("writeback_target"),
                    "max_score_override": (
                        _decimal(max_score_override, fallback="0")
                        if str(max_score_override or "").strip()
                        else None
                    ),
                    "is_required": bool(payload.get("is_required", True)),
                },
            )
            _set_updated_at(ExamSimulation, obj.pk, payload.get("updated_at"))
            return
    except IntegrityError as exc:
        raise SyncDependencyUnavailable(str(exc)) from exc

    raise ValueError("Unsupported content object type.")


def _apply_delete(change):
    from apps.cbt.models import (
        CorrectAnswer,
        Exam,
        ExamBlueprint,
        ExamQuestion,
        ExamSimulation,
        Option,
        Question,
        QuestionBank,
        SimulationWrapper,
    )

    object_type = change.get("object_type")
    object_pk = _as_int(change.get("object_pk"))
    model_lookup = {
        SyncContentObjectType.QUESTION_BANK: QuestionBank,
        SyncContentObjectType.QUESTION: Question,
        SyncContentObjectType.OPTION: Option,
        SyncContentObjectType.CORRECT_ANSWER: CorrectAnswer,
        SyncContentObjectType.EXAM: Exam,
        SyncContentObjectType.EXAM_BLUEPRINT: ExamBlueprint,
        SyncContentObjectType.EXAM_QUESTION: ExamQuestion,
        SyncContentObjectType.SIMULATION_WRAPPER: SimulationWrapper,
        SyncContentObjectType.EXAM_SIMULATION: ExamSimulation,
    }
    model = model_lookup.get(object_type)
    if model is None:
        raise ValueError("Unsupported content object type.")
    model.objects.filter(pk=object_pk).delete()


def apply_cbt_content_changes(*, changes):
    rows = changes if isinstance(changes, list) else []
    summary = {
        "received": len(rows),
        "applied": 0,
        "blocked": 0,
        "last_applied_id": 0,
        "errors": [],
    }
    applied_ids = set()
    pending_rows = [row for row in rows if isinstance(row, dict)]
    if len(pending_rows) != len(rows):
        summary["blocked"] += len(rows) - len(pending_rows)
        summary["errors"].append("Invalid change payload row.")
    with suppress_cbt_change_capture():
        while pending_rows:
            next_pending = []
            pass_progress = False
            for row in pending_rows:
                change_id = _as_int(row.get("id"), fallback=0)
                try:
                    with transaction.atomic():
                        operation = row.get("operation") or SyncContentOperation.UPSERT
                        if operation == SyncContentOperation.DELETE:
                            _apply_delete(row)
                        else:
                            _apply_upsert(row)
                    summary["applied"] += 1
                    applied_ids.add(change_id)
                    pass_progress = True
                except SyncDependencyUnavailable:
                    next_pending.append(row)
                except Exception as exc:
                    summary["blocked"] += 1
                    summary["errors"].append(str(exc))
                    next_pending.extend(
                        pending for pending in pending_rows if pending is not row
                    )
                    pending_rows = []
                    pass_progress = False
                    break
            if not next_pending:
                break
            if not pass_progress:
                summary["blocked"] += len(next_pending)
                for row in next_pending:
                    summary["errors"].append(
                        f"Dependency unavailable for {row.get('object_type')}:{row.get('object_pk')}"
                    )
                break
            pending_rows = next_pending
    for row in rows:
        if not isinstance(row, dict):
            break
        change_id = _as_int(row.get("id"), fallback=0)
        if change_id not in applied_ids:
            break
        summary["last_applied_id"] = change_id
    return summary


def _sync_token():
    return (getattr(settings, "SYNC_ENDPOINT_AUTH_TOKEN", "") or "").strip()


def _sync_cloud_endpoint():
    return (getattr(settings, "SYNC_CLOUD_ENDPOINT", "") or "").strip()


def _sync_pull_timeout():
    value = _as_int(getattr(settings, "SYNC_PULL_TIMEOUT_SECONDS", 5), fallback=5)
    return max(value, 1)


def _fetch_cbt_content_feed(*, after_id, limit):
    endpoint = _sync_cloud_endpoint()
    if not endpoint:
        return {
            "ok": False,
            "status_code": 0,
            "payload": {},
            "error": "Cloud endpoint is not configured.",
        }
    query_string = url_parse.urlencode(
        {
            "after_id": max(_as_int(after_id, fallback=0), 0),
            "limit": max(min(_as_int(limit, fallback=200), 500), 1),
        }
    )
    target_url = f"{endpoint.rstrip('/')}/content/cbt/?{query_string}"
    req = url_request.Request(target_url, method="GET")
    token = _sync_token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with url_request.urlopen(req, timeout=_sync_pull_timeout()) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            payload = json.loads(raw) if raw else {}
            return {
                "ok": 200 <= int(response.status) < 300,
                "status_code": int(response.status),
                "payload": payload if isinstance(payload, dict) else {},
                "error": "",
            }
    except url_error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        payload = {}
        if raw:
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"raw": raw}
        error_message = payload.get("detail") if isinstance(payload, dict) else str(exc)
        return {
            "ok": False,
            "status_code": int(getattr(exc, "code", 0) or 0),
            "payload": payload if isinstance(payload, dict) else {},
            "error": error_message or str(exc),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": 0,
            "payload": {},
            "error": str(exc),
        }


def pull_cbt_content_updates(*, limit=None, max_pages=None):
    if lan_results_only_mode_enabled():
        return {"triggered": False, "reason": "lan_results_only_mode", "applied": 0, "pages": 0}
    if not bool(getattr(settings, "SYNC_PULL_ENABLED", True)):
        return {"triggered": False, "reason": "pull_disabled", "applied": 0, "pages": 0}
    if not _sync_cloud_endpoint():
        return {"triggered": False, "reason": "cloud_not_configured", "applied": 0, "pages": 0}

    safe_limit = max(min(_as_int(limit or getattr(settings, "SYNC_PULL_BATCH_LIMIT", 200)), 500), 1)
    safe_pages = max(_as_int(max_pages or getattr(settings, "SYNC_PULL_MAX_PAGES_PER_RUN", 4)), 1)
    cursor, _ = SyncPullCursor.objects.get_or_create(stream=SyncContentStream.CBT_CONTENT)

    total_applied = 0
    total_blocked = 0
    pages = 0
    last_error = ""
    for _ in range(safe_pages):
        pages += 1
        cursor.last_pull_at = timezone.now()
        cursor.save(update_fields=["last_pull_at", "updated_at"])

        fetch_result = _fetch_cbt_content_feed(after_id=cursor.last_remote_id, limit=safe_limit)
        if not fetch_result["ok"]:
            last_error = fetch_result["error"] or "Unable to fetch cloud content feed."
            cursor.last_error = last_error
            cursor.save(update_fields=["last_error", "updated_at"])
            break

        payload = fetch_result.get("payload") or {}
        changes = payload.get("changes") or []
        if not isinstance(changes, list) or not changes:
            cursor.last_error = ""
            cursor.last_success_at = timezone.now()
            cursor.metadata = {
                "last_count": 0,
                "has_more": bool(payload.get("has_more", False)),
                "next_after_id": payload.get("next_after_id", cursor.last_remote_id),
            }
            cursor.save(update_fields=["last_error", "last_success_at", "metadata", "updated_at"])
            break

        apply_result = apply_cbt_content_changes(changes=changes)
        total_applied += apply_result["applied"]
        total_blocked += apply_result["blocked"]
        if apply_result["applied"] > 0:
            cursor.last_remote_id = max(cursor.last_remote_id, apply_result["last_applied_id"])
            cursor.last_success_at = timezone.now()
            cursor.last_error = ""
            cursor.metadata = {
                "last_count": apply_result["applied"],
                "has_more": bool(payload.get("has_more", False)),
                "next_after_id": payload.get("next_after_id", cursor.last_remote_id),
            }
            cursor.save(
                update_fields=[
                    "last_remote_id",
                    "last_success_at",
                    "last_error",
                    "metadata",
                    "updated_at",
                ]
            )
        if apply_result["blocked"] > 0:
            last_error = (apply_result.get("errors") or ["Sync apply blocked."])[0]
            cursor.last_error = last_error
            cursor.save(update_fields=["last_error", "updated_at"])
            break
        if not bool(payload.get("has_more", False)):
            break

    return {
        "triggered": True,
        "reason": "processed",
        "applied": total_applied,
        "blocked": total_blocked,
        "pages": pages,
        "last_remote_id": cursor.last_remote_id,
        "error": last_error,
    }
