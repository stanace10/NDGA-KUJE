from __future__ import annotations

import base64
import binascii
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.sync.models import SyncOperationType, SyncQueue, SyncQueueStatus
from apps.sync.model_sync import apply_generic_model_payload
from apps.sync.policies import inbound_remote_outbox_allowed
from apps.sync.services import (
    active_session_authority_enforced,
    current_local_node_id,
    current_sync_node_role,
    queue_sync_operation,
)


def _parse_decimal(value, *, fallback="0"):
    candidate = value
    if candidate in (None, ""):
        candidate = fallback
    try:
        return Decimal(str(candidate))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(str(fallback))


def _parse_datetime(value):
    raw = (value or "").strip() if isinstance(value, str) else ""
    if not raw:
        return None
    return parse_datetime(raw.replace("Z", "+00:00"))


def _decode_data_url_file(data_url, *, fallback_name):
    raw = (data_url or "").strip()
    if not raw:
        return None
    if ";base64," not in raw:
        raise ValidationError("Invalid synced image payload.")
    header, encoded = raw.split(";base64,", 1)
    extension = header.replace("data:image/", "").strip().lower()
    if extension not in {"png", "jpg", "jpeg", "webp"}:
        extension = "jpg"
    try:
        decoded = base64.b64decode(encoded)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError("Invalid synced image payload.") from exc
    return ContentFile(decoded, name=f"{fallback_name}.{extension}")


def _apply_student_registration_event(payload):
    from apps.accounts.constants import ROLE_STUDENT
    from apps.accounts.models import Role, StudentProfile, User
    from apps.academics.models import (
        AcademicClass,
        AcademicSession,
        StudentClassEnrollment,
        StudentSubjectEnrollment,
        Subject,
    )

    student_number = (payload.get("student_number") or "").strip().upper()
    username = (payload.get("username") or "").strip()
    if not student_number or not username:
        raise ValidationError("Invalid student registration payload.")

    role_student, _ = Role.objects.get_or_create(code=ROLE_STUDENT, defaults={"name": "Student"})
    profile = StudentProfile.objects.select_related("user").filter(student_number__iexact=student_number).first()
    user = profile.user if profile else None
    username_owner = User.objects.filter(username__iexact=username).first()
    if username_owner and user and username_owner.id != user.id:
        raise ValidationError("Username already belongs to another account.")
    if username_owner and user is None and hasattr(username_owner, "student_profile") and username_owner.student_profile.student_number.upper() != student_number:
        raise ValidationError("Username already belongs to another account.")
    if user is None and username_owner is not None:
        user = username_owner

    created_user = False
    if user is None:
        password = (payload.get("temporary_password") or "").strip() or User.objects.make_random_password()
        user = User.objects.create_user(
            username=username,
            password=password,
            email=(payload.get("email") or "").strip(),
            first_name=(payload.get("first_name") or "").strip(),
            last_name=(payload.get("last_name") or "").strip(),
            primary_role=role_student,
            must_change_password=False,
            password_changed_count=0,
        )
        created_user = True
    else:
        if user.primary_role_id and user.primary_role.code != ROLE_STUDENT:
            raise ValidationError("Student registration dependency unavailable for existing user.")
        user.username = username
        user.email = (payload.get("email") or "").strip()
        user.first_name = (payload.get("first_name") or "").strip()
        user.last_name = (payload.get("last_name") or "").strip()
        user.primary_role = role_student
        user.must_change_password = False
        user.save(
            update_fields=[
                "username",
                "email",
                "first_name",
                "last_name",
                "primary_role",
                "must_change_password",
            ]
        )

    profile, _ = StudentProfile.objects.get_or_create(
        user=user,
        defaults={"student_number": student_number},
    )
    profile.student_number = student_number
    profile.middle_name = (payload.get("middle_name") or "").strip()
    profile.admission_date = parse_date((payload.get("admission_date") or "").strip())
    profile.date_of_birth = parse_date((payload.get("date_of_birth") or "").strip())
    profile.gender = (payload.get("gender") or "").strip()
    profile.guardian_name = (payload.get("guardian_name") or "").strip()
    profile.guardian_phone = (payload.get("guardian_phone") or "").strip()
    profile.guardian_email = (payload.get("guardian_email") or "").strip()
    profile.address = (payload.get("address") or "").strip()
    profile.state_of_origin = (payload.get("state_of_origin") or "").strip()
    profile.nationality = (payload.get("nationality") or "Nigerian").strip() or "Nigerian"
    profile.is_graduated = bool(payload.get("is_graduated", False))
    photo_file = _decode_data_url_file(
        payload.get("profile_photo_data_url"),
        fallback_name=f"sync-student-{student_number.lower().replace('/', '-')}",
    )
    if photo_file is not None:
        profile.profile_photo.save(photo_file.name, photo_file, save=False)
    profile.save()

    session_name = (payload.get("current_session_name") or "").strip()
    class_code = (payload.get("current_class_code") or "").strip().upper()
    subject_codes = [str(code).strip().upper() for code in (payload.get("subject_codes") or []) if str(code).strip()]
    if session_name and class_code:
        session = AcademicSession.objects.filter(name__iexact=session_name).first()
        academic_class = AcademicClass.objects.filter(code__iexact=class_code).first()
        if session is None or academic_class is None:
            raise ValidationError("Dependency unavailable for synced student enrollment.")
        StudentClassEnrollment.objects.update_or_create(
            student=user,
            session=session,
            defaults={"academic_class": academic_class, "is_active": True},
        )
        resolved_subjects = {subject.code.upper(): subject for subject in Subject.objects.filter(code__in=subject_codes)}
        missing_subject_codes = [code for code in subject_codes if code not in resolved_subjects]
        if missing_subject_codes:
            raise ValidationError("Dependency unavailable for synced student subjects.")
        existing_rows = StudentSubjectEnrollment.objects.filter(student=user, session=session)
        selected_ids = {subject.id for subject in resolved_subjects.values()}
        for row in existing_rows:
            should_be_active = row.subject_id in selected_ids
            if row.is_active != should_be_active:
                row.is_active = should_be_active
                row.save(update_fields=["is_active", "updated_at"])
        existing_subject_ids = set(existing_rows.values_list("subject_id", flat=True))
        for code in subject_codes:
            subject = resolved_subjects[code]
            if subject.id not in existing_subject_ids:
                StudentSubjectEnrollment.objects.create(
                    student=user,
                    subject=subject,
                    session=session,
                    is_active=True,
                )

    return {"reference": student_number, "created": created_user}


def _remote_high_stakes_sync_blocked(source_node_id):
    if not active_session_authority_enforced():
        return False
    if current_sync_node_role() != "LAN":
        return False
    normalized_source = (source_node_id or "").strip()
    if not normalized_source:
        return False
    return normalized_source != current_local_node_id()


def _parse_attempt_locator(payload):
    exam_id = payload.get("exam_id")
    student_id = payload.get("student_id")
    attempt_number = payload.get("attempt_number") or 1
    try:
        return int(exam_id), int(student_id), int(attempt_number)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Invalid exam attempt locator payload.") from exc


def _apply_cbt_attempt_event(payload, *, source_node_id=""):
    from apps.cbt.models import CBTExamStatus, Exam, ExamAttempt

    exam_id, student_id, attempt_number = _parse_attempt_locator(payload)
    if _remote_high_stakes_sync_blocked(source_node_id):
        exam = Exam.objects.filter(id=exam_id).only("status").first()
        if exam is not None and exam.status == CBTExamStatus.ACTIVE:
            raise ValidationError("Authority unavailable for active LAN CBT session. Retry later.")
    defaults = {
        "status": payload.get("status", "IN_PROGRESS"),
        "is_locked": bool(payload.get("is_locked", False)),
        "objective_score": _parse_decimal(payload.get("objective_score"), fallback="0"),
        "theory_score": _parse_decimal(payload.get("theory_score"), fallback="0"),
        "total_score": _parse_decimal(payload.get("total_score"), fallback="0"),
        "writeback_metadata": payload.get("writeback_metadata")
        if isinstance(payload.get("writeback_metadata"), dict)
        else {},
    }
    attempt, _ = ExamAttempt.objects.get_or_create(
        exam_id=exam_id,
        student_id=student_id,
        attempt_number=attempt_number,
        defaults=defaults,
    )
    attempt.status = payload.get("status", attempt.status)
    attempt.is_locked = bool(payload.get("is_locked", attempt.is_locked))
    attempt.objective_score = _parse_decimal(payload.get("objective_score"), fallback=str(attempt.objective_score))
    attempt.theory_score = _parse_decimal(payload.get("theory_score"), fallback=str(attempt.theory_score))
    attempt.total_score = _parse_decimal(payload.get("total_score"), fallback=str(attempt.total_score))
    attempt.writeback_metadata = (
        payload.get("writeback_metadata")
        if isinstance(payload.get("writeback_metadata"), dict)
        else attempt.writeback_metadata
    )

    started_at = _parse_datetime(payload.get("started_at"))
    submitted_at = _parse_datetime(payload.get("submitted_at"))
    finalized_at = _parse_datetime(payload.get("finalized_at"))
    if started_at is not None:
        attempt.started_at = started_at
    if submitted_at is not None:
        attempt.submitted_at = submitted_at
    if finalized_at is not None:
        attempt.finalized_at = finalized_at

    attempt.save(
        update_fields=[
            "status",
            "is_locked",
            "objective_score",
            "theory_score",
            "total_score",
            "writeback_metadata",
            "started_at",
            "submitted_at",
            "finalized_at",
            "updated_at",
        ]
    )
    return {"reference": str(attempt.id)}


def _apply_cbt_simulation_event(payload, *, source_node_id=""):
    from apps.cbt.models import CBTExamStatus, Exam, SimulationAttemptRecord

    exam_id, student_id, attempt_number = _parse_attempt_locator(payload)
    if _remote_high_stakes_sync_blocked(source_node_id):
        exam = Exam.objects.filter(id=exam_id).only("status").first()
        if exam is not None and exam.status == CBTExamStatus.ACTIVE:
            raise ValidationError("Authority unavailable for active LAN CBT session. Retry later.")
    try:
        exam_simulation_id = int(payload.get("exam_simulation_id"))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Invalid simulation payload.") from exc

    from apps.cbt.models import ExamAttempt

    attempt = ExamAttempt.objects.filter(
        exam_id=exam_id,
        student_id=student_id,
        attempt_number=attempt_number,
    ).first()
    if attempt is None:
        raise ValidationError("Attempt dependency unavailable for simulation sync.")

    record, _ = SimulationAttemptRecord.objects.get_or_create(
        attempt=attempt,
        exam_simulation_id=exam_simulation_id,
    )
    record.status = payload.get("status", record.status)
    raw_score = payload.get("raw_score")
    final_score = payload.get("final_score")
    imported_score = payload.get("imported_score")
    record.raw_score = (
        _parse_decimal(raw_score, fallback="0")
        if str(raw_score or "").strip()
        else None
    )
    record.final_score = (
        _parse_decimal(final_score, fallback="0")
        if str(final_score or "").strip()
        else None
    )
    record.imported_target = payload.get("imported_target", record.imported_target)
    record.imported_score = (
        _parse_decimal(imported_score, fallback="0")
        if str(imported_score or "").strip()
        else None
    )
    record.save(
        update_fields=[
            "status",
            "raw_score",
            "final_score",
            "imported_target",
            "imported_score",
            "updated_at",
        ]
    )
    return {"reference": str(record.id)}


def _resolve_vote_locator(*, object_ref, conflict_key):
    raw = (conflict_key or "").strip()
    if raw:
        chunks = raw.split(":")
        if len(chunks) == 3:
            return tuple(chunks)
    source = (object_ref or "").strip()
    if source.startswith("vote:"):
        chunks = source.replace("vote:", "", 1).split(":")
        if len(chunks) == 3:
            return tuple(chunks)
    raise ValidationError("Invalid vote locator payload.")


def _apply_election_vote_event(*, payload, object_ref="", conflict_key="", source_node_id=""):
    from apps.elections.models import Election, ElectionStatus, Vote, VoteAudit

    election_id, position_id, voter_id = _resolve_vote_locator(
        object_ref=object_ref,
        conflict_key=conflict_key,
    )
    if _remote_high_stakes_sync_blocked(source_node_id):
        local_election = Election.objects.filter(id=int(election_id)).only("status").first()
        if local_election is not None and local_election.status == ElectionStatus.OPEN:
            raise ValidationError("Authority unavailable for active LAN election session. Retry later.")

    try:
        candidate_id = int(payload.get("candidate_id"))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Invalid candidate payload.") from exc

    vote, _ = Vote.objects.get_or_create(
        election_id=int(election_id),
        position_id=int(position_id),
        voter_id=int(voter_id),
        defaults={
            "candidate_id": candidate_id,
            "submission_token": (payload.get("submission_token") or "")[:96],
        },
    )
    if vote.candidate_id != candidate_id:
        vote.candidate_id = candidate_id
        vote.save(update_fields=["candidate_id", "updated_at"])
    VoteAudit.objects.get_or_create(
        vote=vote,
        defaults={
            "metadata": {
                "synced": True,
                "submitted_at": payload.get("submitted_at", ""),
            }
        },
    )
    return {"reference": str(vote.id)}


def _apply_remote_operation(*, operation_type, payload, object_ref="", conflict_key="", source_node_id=""):
    if operation_type == SyncOperationType.CBT_EXAM_ATTEMPT:
        return _apply_cbt_attempt_event(payload, source_node_id=source_node_id)
    if operation_type == SyncOperationType.CBT_SIMULATION_ATTEMPT:
        return _apply_cbt_simulation_event(payload, source_node_id=source_node_id)
    if operation_type == SyncOperationType.CBT_CONTENT_CHANGE:
        from apps.sync.content_sync import apply_cbt_content_changes

        apply_result = apply_cbt_content_changes(changes=[payload])
        if apply_result["blocked"]:
            raise ValidationError((apply_result.get("errors") or ["CBT content sync blocked."])[0])
        return {"reference": str(payload.get("object_pk") or payload.get("id") or "")}
    if operation_type == SyncOperationType.STUDENT_REGISTRATION_UPSERT:
        return _apply_student_registration_event(payload)
    if operation_type == SyncOperationType.ELECTION_VOTE_SUBMISSION:
        return _apply_election_vote_event(
            payload=payload,
            object_ref=object_ref,
            conflict_key=conflict_key,
            source_node_id=source_node_id,
        )
    if operation_type in {
        SyncOperationType.MODEL_RECORD_UPSERT,
        SyncOperationType.MODEL_RECORD_DELETE,
    }:
        return apply_generic_model_payload(
            payload=payload,
            operation_type=operation_type,
        )
    raise ValidationError("Unsupported sync operation type.")


def ingest_remote_outbox_event(*, envelope, force_reapply=False):
    if not inbound_remote_outbox_allowed():
        raise ValidationError(
            "Cloud-to-LAN outbox sync is disabled in LAN results-only mode. Pull payment deltas instead."
        )
    payload = envelope.get("payload")
    operation_type = (envelope.get("operation_type") or "").strip()
    idempotency_key = (envelope.get("idempotency_key") or "").strip()
    if not isinstance(payload, dict):
        raise ValidationError("Payload must be a JSON object.")
    if not operation_type:
        raise ValidationError("Operation type is required.")
    if not idempotency_key:
        raise ValidationError("Idempotency key is required.")

    queue_row, created = queue_sync_operation(
        operation_type=operation_type,
        payload=payload,
        object_ref=(envelope.get("object_ref") or "")[:120],
        source_portal="remote",
        idempotency_key=idempotency_key[:120],
        conflict_rule=envelope.get("conflict_rule") or "APPEND_ONLY",
        conflict_key=(envelope.get("conflict_key") or "")[:120],
        max_retries=0,
        local_node_id=(envelope.get("local_node_id") or "")[:80],
    )
    if not created and queue_row.status == SyncQueueStatus.SYNCED and not force_reapply:
        return {"status": "duplicate", "reference": queue_row.remote_reference}

    try:
        with transaction.atomic():
            result = _apply_remote_operation(
                operation_type=operation_type,
                payload=payload,
                object_ref=envelope.get("object_ref") or "",
                conflict_key=envelope.get("conflict_key") or "",
                source_node_id=envelope.get("local_node_id") or "",
            )
    except ValidationError as exc:
        detail = "; ".join(exc.messages)
        dependency_error = "dependency" in detail.lower() or "authority" in detail.lower()
        queue_row.status = SyncQueueStatus.RETRY if dependency_error else SyncQueueStatus.FAILED
        queue_row.last_attempt_at = timezone.now()
        queue_row.next_retry_at = timezone.now() if dependency_error else None
        queue_row.last_error = detail
        queue_row.response_payload = {"detail": queue_row.last_error}
        queue_row.response_code = 503 if dependency_error else 422
        queue_row.save(
            update_fields=[
                "status",
                "last_attempt_at",
                "next_retry_at",
                "last_error",
                "response_payload",
                "response_code",
                "updated_at",
            ]
        )
        if dependency_error:
            raise ValidationError("Dependency unavailable. Retry later.")
        raise
    except IntegrityError as exc:
        queue_row.status = SyncQueueStatus.RETRY
        queue_row.last_attempt_at = timezone.now()
        queue_row.next_retry_at = timezone.now()
        queue_row.last_error = str(exc)
        queue_row.response_payload = {"detail": str(exc)}
        queue_row.response_code = 503
        queue_row.save(
            update_fields=[
                "status",
                "last_attempt_at",
                "next_retry_at",
                "last_error",
                "response_payload",
                "response_code",
                "updated_at",
            ]
        )
        raise ValidationError("Dependency unavailable. Retry later.")

    queue_row.status = SyncQueueStatus.SYNCED
    queue_row.synced_at = timezone.now()
    queue_row.last_attempt_at = queue_row.synced_at
    queue_row.next_retry_at = None
    queue_row.last_error = ""
    queue_row.response_code = 200
    queue_row.response_payload = {"status": "applied", **result}
    queue_row.remote_reference = (result.get("reference") or "")[:150]
    queue_row.save(
        update_fields=[
            "status",
            "synced_at",
            "last_attempt_at",
            "next_retry_at",
            "last_error",
            "response_code",
            "response_payload",
            "remote_reference",
            "updated_at",
        ]
    )
    return {
        "status": "reapplied" if force_reapply and not created else "applied",
        "reference": queue_row.remote_reference,
    }
