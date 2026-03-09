from __future__ import annotations

from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from apps.accounts.constants import (
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_STUDENT,
    ROLE_VP,
)
from apps.academics.models import StudentClassEnrollment
from apps.audit.models import AuditCategory, AuditStatus
from apps.audit.services import get_client_ip, log_election_vote, log_event
from apps.elections.models import (
    Candidate,
    Election,
    ElectionResultArtifact,
    ElectionStatus,
    Position,
    Vote,
    VoteAudit,
    VoterGroup,
)
from apps.notifications.services import notify_election_announcement
from apps.pdfs.services import (
    payload_sha256,
    qr_code_data_uri,
    render_pdf_bytes,
    school_logo_data_uri,
)
from apps.sync.services import queue_vote_submission_sync
from apps.tenancy.utils import build_portal_url


def election_ws_group_name(election_id):
    return f"election_analytics_{election_id}"


def _voter_group_queryset(election):
    return election.voter_groups.filter(is_active=True).prefetch_related(
        "roles",
        "academic_classes",
        "users",
    )


def eligible_voter_queryset(election):
    groups = list(_voter_group_queryset(election))
    if not groups:
        return election.votes.none().model.objects.none()

    from apps.accounts.models import User  # local import to avoid circulars

    user_ids = set()
    for group in groups:
        if group.include_all_students:
            user_ids.update(
                User.objects.filter(
                    Q(primary_role__code=ROLE_STUDENT) | Q(secondary_roles__code=ROLE_STUDENT)
                )
                .distinct()
                .values_list("id", flat=True)
            )
        if group.include_all_staff:
            user_ids.update(
                User.objects.filter(
                    Q(primary_role__code__in=[
                        "SUBJECT_TEACHER",
                        "FORM_TEACHER",
                        "DEAN",
                        "BURSAR",
                        "VP",
                        "PRINCIPAL",
                        ROLE_IT_MANAGER,
                    ])
                    | Q(
                        secondary_roles__code__in=[
                            "SUBJECT_TEACHER",
                            "FORM_TEACHER",
                            "DEAN",
                            "BURSAR",
                            "VP",
                            "PRINCIPAL",
                            ROLE_IT_MANAGER,
                        ]
                    )
                )
                .distinct()
                .values_list("id", flat=True)
            )
        group_roles = list(group.roles.values_list("code", flat=True))
        if group_roles:
            user_ids.update(
                User.objects.filter(
                    Q(primary_role__code__in=group_roles)
                    | Q(secondary_roles__code__in=group_roles)
                )
                .distinct()
                .values_list("id", flat=True)
            )
        class_ids = list(group.academic_classes.values_list("id", flat=True))
        if class_ids:
            enrollment_qs = StudentClassEnrollment.objects.filter(
                academic_class_id__in=class_ids,
                is_active=True,
            )
            if election.session_id:
                enrollment_qs = enrollment_qs.filter(session_id=election.session_id)
            user_ids.update(enrollment_qs.values_list("student_id", flat=True))
        user_ids.update(group.users.values_list("id", flat=True))

    if not user_ids:
        return User.objects.none()

    queryset = User.objects.filter(id__in=user_ids, is_active=True)
    if not election.allow_staff_admin_voting:
        queryset = queryset.filter(
            Q(primary_role__code=ROLE_STUDENT) | Q(secondary_roles__code=ROLE_STUDENT)
        )
    return queryset.distinct().order_by("username")


def is_user_eligible_voter(*, election, user):
    if not getattr(user, "is_authenticated", False):
        return False
    return eligible_voter_queryset(election).filter(id=user.id).exists()


def ordered_positions(election):
    return list(election.positions.filter(is_active=True).order_by("sort_order", "name"))


def voted_position_ids(*, election, user):
    return set(
        Vote.objects.filter(election=election, voter=user).values_list("position_id", flat=True)
    )


def remaining_positions_for_voter(*, election, user):
    positions = ordered_positions(election)
    done = voted_position_ids(election=election, user=user)
    return [row for row in positions if row.id not in done]


def _candidate_display(candidate):
    return candidate.display_name or candidate.user.get_full_name() or candidate.user.username


def election_turnout_counts(election):
    eligible_count = eligible_voter_queryset(election).count()
    voted_count = (
        Vote.objects.filter(election=election)
        .values("voter_id")
        .distinct()
        .count()
    )
    turnout = Decimal("0.00")
    if eligible_count > 0:
        turnout = (Decimal(voted_count) / Decimal(eligible_count) * Decimal("100")).quantize(
            Decimal("0.01")
        )
    return eligible_count, voted_count, turnout


def build_election_analytics_payload(election):
    eligible_count, voted_count, turnout = election_turnout_counts(election)
    positions_data = []
    for position in ordered_positions(election):
        candidate_rows = list(
            position.candidates.filter(is_active=True)
            .annotate(vote_count=Count("votes"))
            .order_by("-vote_count", "user__username")
            .values(
                "id",
                "display_name",
                "user__username",
                "vote_count",
            )
        )
        for row in candidate_rows:
            if not row["display_name"]:
                row["display_name"] = row["user__username"]
        max_votes = max((row["vote_count"] for row in candidate_rows), default=0)
        winners = [
            row["display_name"]
            for row in candidate_rows
            if max_votes > 0 and row["vote_count"] == max_votes
        ]
        positions_data.append(
            {
                "position_id": position.id,
                "position_name": position.name,
                "candidate_rows": candidate_rows,
                "max_votes": max_votes,
                "winners": winners,
            }
        )

    return {
        "election_id": election.id,
        "election_title": election.title,
        "status": election.status,
        "eligible_voters": eligible_count,
        "votes_cast": voted_count,
        "turnout_percent": str(turnout),
        "positions": positions_data,
        "updated_at": timezone.now().isoformat(),
    }


def broadcast_election_analytics(election):
    layer = get_channel_layer()
    if not layer:
        return
    payload = build_election_analytics_payload(election)
    async_to_sync(layer.group_send)(
        election_ws_group_name(election.id),
        {
            "type": "election.analytics_update",
            "payload": payload,
        },
    )


def _ensure_vote_ready(*, election, voter, choices_map):
    if election.status != ElectionStatus.OPEN:
        raise ValidationError("Election is not open for voting.")
    if not is_user_eligible_voter(election=election, user=voter):
        raise ValidationError("You are not eligible to vote in this election.")
    if not choices_map:
        raise ValidationError("No vote selections submitted.")

    position_lookup = {
        row.id: row for row in ordered_positions(election)
    }
    if not position_lookup:
        raise ValidationError("Election has no active positions.")
    for position_id, candidate_id in choices_map.items():
        if position_id not in position_lookup:
            raise ValidationError("Invalid position in submitted vote.")
        if Vote.objects.filter(election=election, position_id=position_id, voter=voter).exists():
            raise ValidationError("You already voted for one or more submitted positions.")
        if not Candidate.objects.filter(
            id=candidate_id,
            position_id=position_id,
            position__election=election,
            is_active=True,
        ).exists():
            raise ValidationError("Invalid candidate selection.")


@transaction.atomic
def submit_vote_bundle(
    *,
    election,
    voter,
    choices_map,
    request=None,
    submission_token="",
):
    normalized = {}
    for key, value in (choices_map or {}).items():
        try:
            position_id = int(key)
            candidate_id = int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Invalid vote payload.") from exc
        normalized[position_id] = candidate_id

    _ensure_vote_ready(election=election, voter=voter, choices_map=normalized)
    created_votes = []
    user_agent = ""
    if request:
        user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:512]
    ip_address = get_client_ip(request) if request else None

    try:
        for position_id, candidate_id in normalized.items():
            vote = Vote.objects.create(
                election=election,
                position_id=position_id,
                candidate_id=candidate_id,
                voter=voter,
                submission_token=(submission_token or "")[:96],
            )
            VoteAudit.objects.create(
                vote=vote,
                ip_address=ip_address,
                device=user_agent[:255],
                user_agent=user_agent,
                metadata={"submission_token": submission_token},
            )
            queue_vote_submission_sync(
                election_id=str(election.id),
                position_id=str(position_id),
                voter_id=str(voter.id),
                payload={
                    "vote_id": str(vote.id),
                    "candidate_id": str(candidate_id),
                    "submitted_at": vote.created_at.isoformat(),
                },
                idempotency_key=f"vote-{vote.id}",
            )
            log_election_vote(
                actor=voter,
                request=request,
                metadata={
                    "election_id": str(election.id),
                    "position_id": str(position_id),
                    "candidate_id": str(candidate_id),
                    "vote_id": str(vote.id),
                },
            )
            created_votes.append(vote)
    except IntegrityError as exc:
        raise ValidationError("Duplicate vote blocked by election policy.") from exc

    broadcast_election_analytics(election)
    return created_votes


def can_view_live_analytics(user):
    return (
        user.has_role(ROLE_IT_MANAGER)
        or user.has_role(ROLE_PRINCIPAL)
        or user.has_role(ROLE_VP)
    )


def open_election(*, election, actor, request=None):
    if election.status == ElectionStatus.OPEN:
        return election
    if not election.positions.filter(is_active=True).exists():
        raise ValidationError("Add at least one position before opening election.")
    if not Candidate.objects.filter(position__election=election, is_active=True).exists():
        raise ValidationError("Add at least one active candidate before opening election.")
    if not election.voter_groups.filter(is_active=True).exists():
        raise ValidationError("Configure at least one active voter group before opening election.")

    election.status = ElectionStatus.OPEN
    election.opened_at = timezone.now()
    election.opened_by = actor
    election.closed_at = None
    election.closed_by = None
    election.save(
        update_fields=[
            "status",
            "opened_at",
            "opened_by",
            "closed_at",
            "closed_by",
            "updated_at",
        ]
    )
    recipients = list(eligible_voter_queryset(election))
    if recipients:
        notify_election_announcement(
            recipients=recipients,
            title=f"Election Open: {election.title}",
            message=(
                f"Voting is now open for {election.title}. "
                "Login to election portal and cast your vote."
            ),
            actor=actor,
            request=request,
            action_url="/elections/",
        )
    log_event(
        category=AuditCategory.ELECTION,
        event_type="ELECTION_OPENED",
        status=AuditStatus.SUCCESS,
        actor=actor,
        request=request,
        metadata={"election_id": str(election.id)},
    )
    broadcast_election_analytics(election)
    return election


def close_election(*, election, actor, request=None):
    if election.status == ElectionStatus.CLOSED:
        return election
    election.status = ElectionStatus.CLOSED
    election.closed_at = timezone.now()
    election.closed_by = actor
    election.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
    log_event(
        category=AuditCategory.ELECTION,
        event_type="ELECTION_CLOSED",
        status=AuditStatus.SUCCESS,
        actor=actor,
        request=request,
        metadata={"election_id": str(election.id)},
    )
    broadcast_election_analytics(election)
    return election


def election_summary_payload(election):
    analytics = build_election_analytics_payload(election)
    published_at = timezone.now()
    return {
        "election_id": election.id,
        "title": election.title,
        "description": election.description,
        "session_name": election.session.name if election.session_id else "",
        "status": election.status,
        "starts_at": election.starts_at,
        "ends_at": election.ends_at,
        "published_at": published_at,
        "analytics": analytics,
    }


def generate_election_result_pdf(*, request, election, generated_by):
    payload = election_summary_payload(election)
    digest = payload_sha256(payload)
    artifact = ElectionResultArtifact.objects.create(
        election=election,
        generated_by=generated_by if getattr(generated_by, "is_authenticated", False) else None,
        payload_hash=digest,
        published_at=payload["published_at"],
        metadata={"positions": len(payload["analytics"]["positions"])},
    )
    verification_url = build_portal_url(
        request,
        "landing",
        reverse("elections:verify-result", kwargs={"artifact_id": artifact.id}),
        query={"hash": artifact.payload_hash},
    )
    context = {
        "payload": payload,
        "artifact": artifact,
        "generated_at": timezone.now(),
        "logo_data_uri": school_logo_data_uri(),
        "watermark_data_uri": school_logo_data_uri(),
        "verification_url": verification_url,
        "verification_qr_data_uri": qr_code_data_uri(verification_url),
    }
    pdf_bytes = render_pdf_bytes(template_name="elections/result_pdf.html", context=context)
    log_event(
        category=AuditCategory.ELECTION,
        event_type="ELECTION_RESULT_PDF_GENERATED",
        status=AuditStatus.SUCCESS,
        actor=generated_by if getattr(generated_by, "is_authenticated", False) else None,
        request=request,
        metadata={
            "election_id": str(election.id),
            "artifact_id": str(artifact.id),
        },
    )
    return pdf_bytes, artifact
