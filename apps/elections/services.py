from __future__ import annotations

import re
from decimal import Decimal
from datetime import datetime
from pathlib import Path

from django.conf import settings
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


PREFECT_SCHEDULE_PATTERN = re.compile(
    r"(?P<year>\d{4})\s+(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+time\s+"
    r"(?P<start>\d{1,2}(?::\d{2})?\s*(?:am|pm))\s+to\s+(?P<end>\d{1,2}(?::\d{2})?\s*(?:am|pm))",
    re.IGNORECASE,
)
PREFECT_HEADING_PATTERN = re.compile(r"^\*\*(.+?)\*\*.*$")
PREFECT_BULLET_PATTERN = re.compile(r"^\*\s+(.+?)\s*$")
PREFECT_INLINE_HEADING_PATTERN = re.compile(r"\*\*(.+?)\*\*")


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
                    staff_profile__isnull=False
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


def ensure_default_voter_groups(*, election):
    group_specs = [
        {
            "name": "All Students",
            "description": "Quick setup group for every active student voter.",
            "include_all_students": True,
            "include_all_staff": False,
        },
        {
            "name": "All Staff/Admin",
            "description": "Quick setup group for every active staff/admin voter.",
            "include_all_students": False,
            "include_all_staff": True,
        },
    ]
    results = []
    for spec in group_specs:
        group, created = VoterGroup.objects.get_or_create(
            election=election,
            name=spec["name"],
            defaults={**spec, "is_active": True},
        )
        changed_fields = []
        for field, value in {**spec, "is_active": True}.items():
            if getattr(group, field) != value:
                setattr(group, field, value)
                changed_fields.append(field)
        if changed_fields:
            changed_fields.append("updated_at")
            group.save(update_fields=changed_fields)
        results.append(
            {
                "group": group,
                "created": created,
                "updated": bool(changed_fields) and not created,
            }
        )
    return results


def _split_candidate_entry_line(raw_line):
    for delimiter in ("|", "\t", ","):
        if delimiter in raw_line:
            return delimiter, [part.strip() for part in raw_line.split(delimiter)]
    return "", [raw_line.strip()]


def _normalize_person_text(raw_value):
    return re.sub(r"\s+", " ", (raw_value or "").strip()).strip()


def _normalize_name_token(raw_value):
    normalized = re.sub(r"[^a-z0-9]", "", (raw_value or "").casefold())
    return {
        "favour": "favor",
        "somma": "soma",
    }.get(normalized, normalized)


def _name_tokens(raw_value):
    ignored_tokens = {"ss1", "ss2", "ss3", "js1", "js2", "js3", "student", "prefect", "assistant"}
    return [
        _normalize_name_token(token)
        for token in re.findall(r"[A-Za-z0-9]+", _normalize_person_text(raw_value))
        if _normalize_name_token(token) and _normalize_name_token(token) not in ignored_tokens
    ]


def _token_matches(query_token, candidate_token):
    if query_token == candidate_token:
        return True
    if len(query_token) == 1 and candidate_token.startswith(query_token):
        return True
    if len(candidate_token) == 1 and query_token.startswith(candidate_token):
        return True
    if min(len(query_token), len(candidate_token)) >= 4:
        if query_token.startswith(candidate_token) or candidate_token.startswith(query_token):
            return True
    return False


def _tokens_match_name(query_tokens, candidate_tokens):
    if not query_tokens or not candidate_tokens:
        return False
    if len(query_tokens) > len(candidate_tokens):
        return False
    candidate_index = 0
    for query_token in query_tokens:
        matched = False
        while candidate_index < len(candidate_tokens):
            candidate_token = candidate_tokens[candidate_index]
            candidate_index += 1
            if _token_matches(query_token, candidate_token):
                matched = True
                break
        if not matched:
            return False
    return True


def _user_name_variants(user):
    first_name = _normalize_person_text(getattr(user, "first_name", ""))
    last_name = _normalize_person_text(getattr(user, "last_name", ""))
    middle_name = _normalize_person_text(
        getattr(getattr(user, "student_profile", None), "middle_name", "")
    )
    variants = {
        _normalize_person_text(user.get_full_name()),
        _normalize_person_text(getattr(user, "display_name", "")),
        _normalize_person_text(getattr(user, "username", "")),
    }
    if last_name and first_name:
        variants.add(_normalize_person_text(f"{last_name} {first_name}"))
        if middle_name:
            variants.add(_normalize_person_text(f"{last_name} {first_name} {middle_name}"))
            variants.add(_normalize_person_text(f"{first_name} {middle_name} {last_name}"))
        else:
            variants.add(_normalize_person_text(f"{first_name} {last_name}"))
    return {row for row in variants if row}


def _resolve_candidate_lookup_user_by_name(*, user_lookup):
    from apps.accounts.models import User  # local import to avoid circulars

    query_tokens = _name_tokens(user_lookup)
    if not query_tokens:
        return None, False

    matches = []
    for user in (
        User.objects.filter(
            Q(student_profile__isnull=False) | Q(staff_profile__isnull=False)
        )
        .select_related("student_profile", "staff_profile", "primary_role")
        .distinct()
    ):
        candidate_variants = [_name_tokens(row) for row in _user_name_variants(user)]
        if any(_tokens_match_name(query_tokens, candidate_tokens) for candidate_tokens in candidate_variants):
            matches.append(user)

    if len(matches) == 1:
        return matches[0], False
    if len(matches) > 1:
        return None, True
    return None, False


def _resolve_candidate_lookup_user(*, user_lookup):
    from apps.accounts.models import User  # local import to avoid circulars

    resolved = (
        User.objects.filter(
            Q(username__iexact=user_lookup)
            | Q(student_profile__student_number__iexact=user_lookup)
            | Q(staff_profile__staff_id__iexact=user_lookup)
        )
        .distinct()
        .first()
    )
    if resolved is not None:
        return resolved, False
    return _resolve_candidate_lookup_user_by_name(user_lookup=user_lookup)


def _parse_prefect_schedule(raw_text):
    match = PREFECT_SCHEDULE_PATTERN.search(raw_text or "")
    if not match:
        return None, None

    day = int(match.group("day"))
    year = int(match.group("year"))
    month = match.group("month")
    start_text = _normalize_person_text(match.group("start")).replace(" ", "").upper()
    end_text = _normalize_person_text(match.group("end")).replace(" ", "").upper()

    for time_format in ("%d %B %Y %I%p", "%d %B %Y %I:%M%p"):
        try:
            start_naive = datetime.strptime(f"{day} {month} {year} {start_text}", time_format)
            end_naive = datetime.strptime(f"{day} {month} {year} {end_text}", time_format)
            return timezone.make_aware(start_naive), timezone.make_aware(end_naive)
        except ValueError:
            continue
    return None, None


def parse_prefect_screening_markdown(*, raw_text):
    sections = []
    current_heading_roles = []
    current_candidates = []

    def flush_section():
        nonlocal current_heading_roles, current_candidates
        if current_heading_roles:
            section_name = " / ".join(current_heading_roles)
            sections.append({"name": section_name, "candidates": list(current_candidates)})
        current_heading_roles = []
        current_candidates = []

    def titleize_heading(raw_value):
        words = [word for word in re.split(r"\s+", _normalize_person_text(raw_value)) if word]
        lower_keep = {"and", "of", "the", "to", "for"}
        normalized_words = []
        for index, word in enumerate(words):
            if word.isupper() and len(word) <= 4:
                normalized_words.append(word)
                continue
            lowered = word.casefold()
            if index > 0 and lowered in lower_keep:
                normalized_words.append(lowered)
                continue
            normalized_words.append(lowered.capitalize())
        return " ".join(normalized_words)

    def canonicalize_role_title(raw_value, previous_title=""):
        cleaned = re.sub(r"\s*\(.*?\)\s*", " ", raw_value or "").strip(" /")
        cleaned = _normalize_person_text(cleaned)
        if not cleaned:
            return ""
        lowered = cleaned.casefold()
        if lowered in {"assistant", "asst"} and previous_title:
            return f"Assistant {previous_title}"
        if lowered in {"deputy"} and previous_title:
            return f"Deputy {previous_title}"
        if lowered.startswith("assistant "):
            return titleize_heading(cleaned)
        if lowered.startswith("deputy "):
            return titleize_heading(cleaned)
        if lowered == "prep prefect":
            return "Prep Prefect"
        return titleize_heading(cleaned)

    def extract_heading_roles(raw_line):
        segments = PREFECT_INLINE_HEADING_PATTERN.findall(raw_line or "")
        if not segments:
            return []
        roles = []

        def append_role(raw_segment):
            segment = re.sub(r"\s*\(.*?\)\s*", " ", raw_segment or "")
            segment = _normalize_person_text(segment)
            if not segment:
                return
            lowered = segment.casefold()
            if lowered in {"/assistant", "assistant"} and roles:
                roles.append(f"Assistant {roles[-1]}")
                return
            if lowered.endswith("/assistant"):
                primary_title = canonicalize_role_title(segment[: -len("/assistant")])
                if primary_title:
                    roles.append(primary_title)
                    roles.append(f"Assistant {primary_title}")
                return
            if "social/it prefect" in lowered:
                roles.extend(["Social Prefect", "IT Prefect"])
                return
            if "/assistant" in lowered:
                primary, _assistant = segment.split("/", 1)
                primary_title = canonicalize_role_title(primary)
                if primary_title:
                    roles.append(primary_title)
                    roles.append(f"Assistant {primary_title}")
                return
            if "/" in segment and lowered not in {"study/prep prefect"}:
                for part in [item.strip() for item in segment.split("/") if item.strip()]:
                    role_title = canonicalize_role_title(
                        part,
                        previous_title=roles[-1] if roles else "",
                    )
                    if role_title:
                        roles.append(role_title)
                return
            role_title = canonicalize_role_title(
                segment,
                previous_title=roles[-1] if roles else "",
            )
            if role_title:
                roles.append(role_title)

        for segment in segments:
            append_role(segment)

        remainder = PREFECT_INLINE_HEADING_PATTERN.sub(" ", raw_line or "")
        if "assistant" in (remainder or "").casefold():
            append_role(remainder)

        deduped = []
        for role in roles:
            if role and role not in deduped:
                deduped.append(role)
        return deduped

    for raw_line in (raw_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.casefold().startswith("non teach"):
            flush_section()
            break
        heading_match = PREFECT_HEADING_PATTERN.match(line) or ("**" in line)
        if heading_match:
            roles = extract_heading_roles(line)
            if roles:
                if current_heading_roles and not current_candidates:
                    for role in roles:
                        if role not in current_heading_roles:
                            current_heading_roles.append(role)
                else:
                    flush_section()
                    current_heading_roles = list(roles)
            continue
        bullet_match = PREFECT_BULLET_PATTERN.match(line)
        if current_heading_roles:
            candidate_name = (bullet_match.group(1).strip() if bullet_match else line.strip()).strip("* ").strip()
            if candidate_name:
                current_candidates.append(candidate_name)
    flush_section()

    positions = []
    for section in sections:
        raw_name = re.sub(r"\s*\(.*?\)\s*", " ", section["name"]).strip()
        if not raw_name:
            continue
        positions.append({"name": raw_name, "candidates": list(section["candidates"])})

    starts_at, ends_at = _parse_prefect_schedule(raw_text)
    return {
        "title": "Screened Candidates For Prefects",
        "starts_at": starts_at,
        "ends_at": ends_at,
        "positions": positions,
    }


@transaction.atomic
def import_candidate_entries(
    *,
    election,
    raw_entries,
    is_active=True,
    update_existing=True,
):
    position_lookup = {
        row.name.casefold(): row
        for row in election.positions.all()
    }
    cleaned_entries = []
    errors = []

    for line_number, raw_line in enumerate((raw_entries or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        delimiter, parts = _split_candidate_entry_line(line)
        if len(parts) < 2:
            errors.append(
                f"Line {line_number}: provide at least Position and User Lookup."
            )
            continue
        position_name = parts[0].strip()
        user_lookup = parts[1].strip()
        display_name = parts[2].strip() if len(parts) > 2 else ""
        manifesto = delimiter.join(parts[3:]).strip() if len(parts) > 3 and delimiter else ""
        position = position_lookup.get(position_name.casefold())
        if not position:
            errors.append(f"Line {line_number}: position '{position_name}' was not found.")
            continue
        user, is_ambiguous = _resolve_candidate_lookup_user(user_lookup=user_lookup)
        if is_ambiguous:
            errors.append(
                f"Line {line_number}: user lookup '{user_lookup}' matched multiple school profiles."
            )
            continue
        if not user:
            errors.append(
                f"Line {line_number}: user '{user_lookup}' was not found by username, student number, staff ID, or school name."
            )
            continue
        cleaned_entries.append(
            {
                "line_number": line_number,
                "position": position,
                "user": user,
                "display_name": display_name,
                "manifesto": manifesto,
            }
        )

    if not cleaned_entries and not errors:
        raise ValidationError("Add at least one candidate line to import.")
    if errors:
        raise ValidationError(errors)

    created_count = 0
    updated_count = 0
    skipped_count = 0
    imported_candidates = []
    for entry in cleaned_entries:
        defaults = {
            "display_name": entry["display_name"],
            "manifesto": entry["manifesto"],
            "is_active": is_active,
        }
        candidate, created = Candidate.objects.get_or_create(
            position=entry["position"],
            user=entry["user"],
            defaults=defaults,
        )
        if created:
            created_count += 1
            imported_candidates.append(candidate)
            continue

        if not update_existing:
            skipped_count += 1
            imported_candidates.append(candidate)
            continue

        changed_fields = []
        for field, value in defaults.items():
            if field in {"display_name", "manifesto"} and not value:
                continue
            if getattr(candidate, field) != value:
                setattr(candidate, field, value)
                changed_fields.append(field)
        if changed_fields:
            changed_fields.append("updated_at")
            candidate.save(update_fields=changed_fields)
            updated_count += 1
        else:
            skipped_count += 1
        imported_candidates.append(candidate)

    return {
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "candidates": imported_candidates,
    }


@transaction.atomic
def import_prefect_screening_markdown(
    *,
    election,
    raw_text,
    is_active=True,
    update_existing=True,
    prepare_voter_groups=True,
    update_election_meta=True,
):
    parsed = parse_prefect_screening_markdown(raw_text=raw_text)
    positions = parsed["positions"]
    if not positions:
        raise ValidationError("No prefect positions were found in the supplied markdown file.")

    existing_positions = {
        row.name.casefold(): row
        for row in election.positions.all()
    }
    created_positions = 0
    updated_positions = 0
    next_sort_order = (
        election.positions.order_by("-sort_order").values_list("sort_order", flat=True).first() or 0
    )
    candidate_lines = []

    for position_spec in positions:
        key = position_spec["name"].casefold()
        position = existing_positions.get(key)
        if position is None:
            next_sort_order += 1
            position = Position.objects.create(
                election=election,
                name=position_spec["name"],
                sort_order=next_sort_order,
                is_active=True,
            )
            existing_positions[key] = position
            created_positions += 1
        else:
            changed_fields = []
            if not position.is_active:
                position.is_active = True
                changed_fields.append("is_active")
            if changed_fields:
                changed_fields.append("updated_at")
                position.save(update_fields=changed_fields)
                updated_positions += 1

        for candidate_name in position_spec["candidates"]:
            candidate_lines.append(f"{position.name}, {candidate_name}, {candidate_name}")

    candidate_result = import_candidate_entries(
        election=election,
        raw_entries="\n".join(candidate_lines),
        is_active=is_active,
        update_existing=update_existing,
    )

    election_fields = []
    if update_election_meta:
        if not election.title.strip():
            election.title = parsed["title"]
            election_fields.append("title")
        if parsed["starts_at"] is not None and election.starts_at != parsed["starts_at"]:
            election.starts_at = parsed["starts_at"]
            election_fields.append("starts_at")
        if parsed["ends_at"] is not None and election.ends_at != parsed["ends_at"]:
            election.ends_at = parsed["ends_at"]
            election_fields.append("ends_at")
        if not election.allow_staff_admin_voting:
            election.allow_staff_admin_voting = True
            election_fields.append("allow_staff_admin_voting")
    if election_fields:
        election_fields.append("updated_at")
        election.save(update_fields=election_fields)

    voter_group_results = []
    if prepare_voter_groups:
        voter_group_results = ensure_default_voter_groups(election=election)

    return {
        "parsed": parsed,
        "created_positions": created_positions,
        "updated_positions": updated_positions,
        "candidate_result": candidate_result,
        "voter_group_results": voter_group_results,
    }


def _candidate_display(candidate):
    return candidate.display_name or candidate.user.get_full_name() or candidate.user.username


def position_rank_titles(position_name):
    raw_name = _normalize_person_text(position_name)
    if " / " in raw_name:
        return [segment.strip() for segment in raw_name.split(" / ") if segment.strip()]
    return [raw_name] if raw_name else []


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
        rank_titles = position_rank_titles(position.name)
        ranked_rows = sorted(
            candidate_rows,
            key=lambda row: (-row["vote_count"], row["display_name"], row["user__username"]),
        )
        ranked_outcomes = []
        for index, role_title in enumerate(rank_titles):
            if index >= len(ranked_rows):
                break
            ranked_row = ranked_rows[index]
            ranked_outcomes.append(
                {
                    "role_title": role_title,
                    "display_name": ranked_row["display_name"],
                    "vote_count": ranked_row["vote_count"],
                }
            )
        positions_data.append(
            {
                "position_id": position.id,
                "position_name": position.name,
                "candidate_rows": candidate_rows,
                "max_votes": max_votes,
                "winners": winners,
                "rank_titles": rank_titles,
                "ranked_outcomes": ranked_outcomes,
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


def build_lan_readiness_payload(*, election):
    root_dir = Path(settings.ROOT_DIR)
    eligible_qs = eligible_voter_queryset(election)
    student_count = eligible_qs.filter(
        Q(primary_role__code=ROLE_STUDENT)
        | Q(secondary_roles__code=ROLE_STUDENT)
        | Q(student_profile__isnull=False)
    ).distinct().count()
    staff_count = eligible_qs.filter(staff_profile__isnull=False).distinct().count()
    checks = [
        {
            "label": "LAN environment file",
            "ok": (root_dir / ".env.lan").exists(),
            "detail": ".env.lan is present for LAN node secrets.",
            "required": True,
        },
        {
            "label": "LAN compose stack",
            "ok": (root_dir / "docker-compose.lan.yml").exists(),
            "detail": "docker-compose.lan.yml is available.",
            "required": True,
        },
        {
            "label": "LAN start script",
            "ok": (root_dir / "scripts" / "start_stage0_services.ps1").exists(),
            "detail": "Local runtime start script is available.",
            "required": True,
        },
        {
            "label": "LAN verification command",
            "ok": (root_dir / "apps" / "dashboard" / "management" / "commands" / "verify_stage0.py").exists(),
            "detail": "manage.py verify_stage0 is available for runtime checks.",
            "required": True,
        },
        {
            "label": "Election positions",
            "ok": election.positions.filter(is_active=True).exists(),
            "detail": "At least one active position is configured.",
            "required": True,
        },
        {
            "label": "Election candidates",
            "ok": Candidate.objects.filter(position__election=election, is_active=True).exists(),
            "detail": "At least one active candidate is configured.",
            "required": True,
        },
        {
            "label": "Student voters ready",
            "ok": student_count > 0,
            "detail": f"{student_count} eligible student voter(s) currently in scope.",
            "required": True,
        },
        {
            "label": "Staff/Admin voters ready",
            "ok": (not election.allow_staff_admin_voting) or staff_count > 0,
            "detail": (
                f"{staff_count} eligible staff/admin voter(s) currently in scope."
                if election.allow_staff_admin_voting
                else "Staff/Admin voting is currently disabled for this election."
            ),
            "required": election.allow_staff_admin_voting,
        },
    ]
    ready = all(check["ok"] for check in checks if check["required"])
    return {
        "ready": ready,
        "eligible_students": student_count,
        "eligible_staff": staff_count,
        "checks": checks,
        "commands": [
            r"powershell -ExecutionPolicy Bypass -File .\scripts\start_stage0_services.ps1",
            r".\.venv\Scripts\python.exe manage.py verify_stage0",
            r"docker compose --env-file .env.lan -f docker-compose.lan.yml up -d --build",
        ],
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


def close_election(*, election, actor=None, request=None, closed_at=None, closure_mode="manual"):
    if election.status == ElectionStatus.CLOSED:
        return election
    closed_at = closed_at or timezone.now()
    election.status = ElectionStatus.CLOSED
    election.closed_at = closed_at
    election.closed_by = actor if getattr(actor, "is_authenticated", False) else None
    election.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
    log_event(
        category=AuditCategory.ELECTION,
        event_type="ELECTION_CLOSED",
        status=AuditStatus.SUCCESS,
        actor=actor,
        request=request,
        metadata={"election_id": str(election.id), "closure_mode": closure_mode},
    )
    broadcast_election_analytics(election)
    return election


def auto_close_due_elections(*, actor=None, request=None, as_of=None):
    as_of = as_of or timezone.now()
    closed_ids = []
    due_elections = (
        Election.objects.filter(
            status=ElectionStatus.OPEN,
            is_active=True,
            ends_at__isnull=False,
            ends_at__lte=as_of,
        )
        .select_related("created_by")
        .order_by("ends_at", "id")
    )
    for election in due_elections:
        close_election(
            election=election,
            actor=actor or election.created_by,
            request=request,
            closed_at=as_of,
            closure_mode="schedule",
        )
        closed_ids.append(election.id)
    return closed_ids


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
