from __future__ import annotations

import html
import http.cookiejar
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.models import User
from apps.academics.models import AcademicClass, Subject, TeacherSubjectAssignment
from apps.cbt.models import CBTExamStatus, CBTExamType, Exam, ExamBlueprint
from apps.setup_wizard.models import SystemSetupState
from apps.sync.content_sync import suppress_cbt_change_capture
from apps.sync.inbound_sync import ingest_remote_outbox_event
from apps.sync.models import SyncOperationType, SyncQueue, SyncQueueStatus


_CSRF_PATTERNS = (
    re.compile(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', re.I),
    re.compile(r'value=["\']([^"\']+)["\']\s+name=["\']csrfmiddlewaretoken["\']', re.I),
)
_ARTICLE_AFTER_HEADING = r"<h2[^>]*>\s*%s\s*</h2>(.*?)</article>"
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)
_PARAGRAPH_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class CloudExamRow:
    exam_id: int
    title: str = ""
    subject_code: str = ""
    subject_name: str = ""
    class_code: str = ""
    created_by_username: str = ""
    activated_by_username: str = ""
    dean_username: str = ""
    status_label: str = ""
    exam_type_label: str = ""
    open_now: bool = False
    is_time_based: bool = True
    schedule_start: str = ""
    schedule_end: str = ""
    duration_minutes: int = 60
    max_attempts: int = 1
    shuffle_questions: bool = True
    shuffle_options: bool = True
    instructions: str = ""


STATUS_VALUE_BY_LABEL = {
    label.strip().lower(): value
    for value, label in CBTExamStatus.choices
}
EXAM_TYPE_VALUE_BY_LABEL = {
    label.strip().lower(): value
    for value, label in CBTExamType.choices
}


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _strip_tags(fragment: str) -> str:
    return _normalize_space(html.unescape(_TAG_RE.sub(" ", fragment or "")))


def _extract_csrf_token(page_html: str) -> str:
    for pattern in _CSRF_PATTERNS:
        match = pattern.search(page_html or "")
        if match:
            return match.group(1).strip()
    return ""


def _build_opener() -> urllib.request.OpenerDirector:
    cookie_jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))


def _fetch_text(*, opener, url, data=None, headers=None, timeout=30) -> str:
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers or {},
        method="POST" if data is not None else "GET",
    )
    with opener.open(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")


def _post_form(*, opener, url, form_data, referer, timeout=30) -> str:
    encoded = urllib.parse.urlencode(form_data).encode("utf-8")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": referer,
    }
    return _fetch_text(opener=opener, url=url, data=encoded, headers=headers, timeout=timeout)


def _extract_article_section(page_html: str, heading: str) -> str:
    pattern = re.compile(_ARTICLE_AFTER_HEADING % re.escape(heading), re.I | re.S)
    match = pattern.search(page_html or "")
    return match.group(1) if match else ""


def _extract_linked_exam_id(fragment: str) -> int | None:
    match = re.search(r"/cbt/it/activation/(\d+)/", fragment or "", re.I)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _extract_paragraph_texts(fragment: str) -> list[str]:
    return [_strip_tags(item) for item in _PARAGRAPH_RE.findall(fragment or "") if _strip_tags(item)]


def _parse_subject_class(text: str) -> tuple[str, str]:
    match = re.search(r"([A-Z0-9]+)\s*/\s*([A-Z0-9-]+)", text or "")
    if not match:
        return "", ""
    return match.group(1).strip().upper(), match.group(2).strip().upper()


def _parse_int(value: str, fallback: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return int(fallback)


def _parse_checkbox(page_html: str, field_name: str) -> bool:
    match = re.search(
        rf"<input[^>]*name=[\"']{re.escape(field_name)}[\"'][^>]*>",
        page_html or "",
        re.I | re.S,
    )
    if not match:
        return False
    return "checked" in match.group(0).lower()


def _parse_input_value(page_html: str, field_name: str) -> str:
    patterns = (
        re.compile(
            rf"<input[^>]*name=[\"']{re.escape(field_name)}[\"'][^>]*value=[\"']([^\"']*)[\"'][^>]*>",
            re.I | re.S,
        ),
        re.compile(
            rf"<input[^>]*value=[\"']([^\"']*)[\"'][^>]*name=[\"']{re.escape(field_name)}[\"'][^>]*>",
            re.I | re.S,
        ),
    )
    for pattern in patterns:
        match = pattern.search(page_html or "")
        if match:
            return html.unescape(match.group(1).strip())
    return ""


def _parse_textarea_value(page_html: str, field_name: str) -> str:
    match = re.search(
        rf"<textarea[^>]*name=[\"']{re.escape(field_name)}[\"'][^>]*>(.*?)</textarea>",
        page_html or "",
        re.I | re.S,
    )
    if not match:
        return ""
    return _normalize_space(html.unescape(match.group(1)))


def _parse_chip_value(page_html: str, label: str) -> str:
    match = re.search(
        rf"{re.escape(label)}\s*([^<]+)",
        page_html or "",
        re.I,
    )
    if not match:
        return ""
    return _normalize_space(html.unescape(match.group(1)))


def _parse_list_page(page_html: str) -> dict[int, CloudExamRow]:
    rows: dict[int, CloudExamRow] = {}

    def merge_row(exam_row: CloudExamRow):
        current = rows.get(exam_row.exam_id)
        if current is None:
            rows[exam_row.exam_id] = exam_row
            return
        for field_name in exam_row.__dataclass_fields__:
            incoming_value = getattr(exam_row, field_name)
            if incoming_value not in ("", None, False):
                setattr(current, field_name, incoming_value)

    def parse_section(section_html: str, section_name: str):
        for row_html in _ROW_RE.findall(section_html or ""):
            cells = _CELL_RE.findall(row_html or "")
            if not cells:
                continue
            exam_id = _extract_linked_exam_id(row_html)
            if exam_id is None:
                continue

            exam_texts = _extract_paragraph_texts(cells[0])
            title = exam_texts[0] if exam_texts else _strip_tags(cells[0])
            subject_code = ""
            class_code = ""
            created_by_username = ""
            activated_by_username = ""
            status_label = ""

            if section_name == "approved" and len(cells) >= 4:
                subject_code, class_code = _parse_subject_class(_strip_tags(cells[1]))
                created_by_username = _strip_tags(cells[2])
                status_label = _strip_tags(cells[3])
            elif section_name == "active" and len(cells) >= 4:
                detail_texts = exam_texts[1] if len(exam_texts) > 1 else ""
                subject_code, class_code = _parse_subject_class(detail_texts)
                created_by_username = _strip_tags(cells[2])
                activated_by_username = _strip_tags(cells[3])
                status_label = "Active"
            elif section_name == "closed" and len(cells) >= 4:
                detail_texts = exam_texts[1] if len(exam_texts) > 1 else ""
                subject_code, class_code = _parse_subject_class(detail_texts)
                created_by_username = _strip_tags(cells[2])
                status_label = _strip_tags(cells[3])

            merge_row(
                CloudExamRow(
                    exam_id=exam_id,
                    title=title,
                    subject_code=subject_code,
                    class_code=class_code,
                    created_by_username=created_by_username,
                    activated_by_username=activated_by_username,
                    status_label=status_label,
                )
            )

    parse_section(_extract_article_section(page_html, "Approved Queue"), "approved")
    parse_section(_extract_article_section(page_html, "Scheduled Exams"), "active")
    parse_section(_extract_article_section(page_html, "Closed History"), "closed")
    return rows


def _parse_detail_page(*, page_html: str, exam_row: CloudExamRow) -> CloudExamRow:
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", page_html or "", re.I | re.S)
    if title_match:
        exam_row.title = _strip_tags(title_match.group(1))

    subtitle_match = re.search(
        r"<p[^>]*class=[\"'][^\"']*mt-1[^\"']*[\"'][^>]*>(.*?)</p>",
        page_html or "",
        re.I | re.S,
    )
    if subtitle_match:
        parts = [_normalize_space(html.unescape(part)) for part in _strip_tags(subtitle_match.group(1)).split("|")]
        if len(parts) >= 1 and not exam_row.subject_name:
            exam_row.subject_name = parts[0]
        if len(parts) >= 2 and not exam_row.class_code:
            exam_row.class_code = parts[1].upper()
        if len(parts) >= 3 and not exam_row.exam_type_label:
            exam_row.exam_type_label = parts[2]

    exam_row.status_label = _parse_chip_value(page_html, "Status:") or exam_row.status_label
    exam_row.dean_username = _parse_chip_value(page_html, "Dean:")
    exam_row.schedule_start = _parse_input_value(page_html, "schedule_start")
    exam_row.schedule_end = _parse_input_value(page_html, "schedule_end")
    exam_row.duration_minutes = _parse_int(
        _parse_input_value(page_html, "duration_minutes"),
        exam_row.duration_minutes or 60,
    )
    exam_row.max_attempts = _parse_int(
        _parse_input_value(page_html, "max_attempts"),
        exam_row.max_attempts or 1,
    )
    exam_row.shuffle_questions = _parse_checkbox(page_html, "shuffle_questions")
    exam_row.shuffle_options = _parse_checkbox(page_html, "shuffle_options")
    exam_row.open_now = _parse_checkbox(page_html, "open_now")
    exam_row.is_time_based = _parse_checkbox(page_html, "is_time_based")
    exam_row.instructions = _parse_textarea_value(page_html, "instructions")
    return exam_row


def _parse_exam_datetime(raw_value: str):
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = parse_datetime(value)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _resolve_required_exam_context(*, row: CloudExamRow, fallback_actor: User, setup_state):
    session = getattr(setup_state, "current_session", None)
    term = getattr(setup_state, "current_term", None)
    if session is None or term is None:
        raise CommandError("Current session/term must be configured before recovering CBT catalog.")

    subject = Subject.objects.filter(code__iexact=row.subject_code).first()
    if subject is None and row.subject_name:
        subject = Subject.objects.filter(name__iexact=row.subject_name).first()
    if subject is None:
        raise CommandError(f"Subject lookup failed for recovered exam {row.exam_id}: {row.subject_code or row.subject_name}")

    academic_class = AcademicClass.objects.filter(code__iexact=row.class_code).first()
    if academic_class is None:
        raise CommandError(f"Class lookup failed for recovered exam {row.exam_id}: {row.class_code}")

    created_by = User.objects.filter(username__iexact=row.created_by_username).first() if row.created_by_username else None
    if created_by is None:
        created_by = fallback_actor
    if created_by is None:
        raise CommandError(f"Teacher lookup failed for recovered exam {row.exam_id}: {row.created_by_username}")

    dean_reviewed_by = None
    if row.dean_username and row.dean_username != "-":
        dean_reviewed_by = User.objects.filter(username__iexact=row.dean_username).first()

    activated_by = None
    if row.activated_by_username and row.activated_by_username != "-":
        activated_by = User.objects.filter(username__iexact=row.activated_by_username).first()

    assignment = TeacherSubjectAssignment.objects.filter(
        teacher=created_by,
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
    ).first()

    return {
        "session": session,
        "term": term,
        "subject": subject,
        "academic_class": academic_class,
        "created_by": created_by,
        "dean_reviewed_by": dean_reviewed_by,
        "activated_by": activated_by,
        "assignment": assignment,
    }


class Command(BaseCommand):
    help = (
        "Recover local CBT exam catalog from the cloud IT activation board "
        "and optionally reapply blocked local CBT attempt sync rows."
    )

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True, help="Cloud staff/principal username.")
        parser.add_argument("--password", required=True, help="Cloud staff/principal password.")
        parser.add_argument(
            "--login-url",
            default="https://it.ndgakuje.org/auth/login/?audience=staff",
            help="Cloud login URL.",
        )
        parser.add_argument(
            "--activation-url",
            default="https://it.ndgakuje.org/cbt/it/activation/",
            help="Cloud IT activation list URL.",
        )
        parser.add_argument(
            "--skip-retry-replay",
            action="store_true",
            help="Recover exam catalog only without reapplying blocked local CBT attempt rows.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and parse cloud metadata without writing local exam rows.",
        )

    def handle(self, *args, **options):
        username = (options["username"] or "").strip()
        password = options["password"] or ""
        login_url = (options["login_url"] or "").strip()
        activation_url = (options["activation_url"] or "").strip()
        skip_retry_replay = bool(options["skip_retry_replay"])
        dry_run = bool(options["dry_run"])

        if not username:
            raise CommandError("Cloud username is required.")
        if not password:
            raise CommandError("Cloud password is required.")
        if not login_url:
            raise CommandError("Cloud login URL is required.")
        if not activation_url:
            raise CommandError("Cloud activation URL is required.")

        opener = _build_opener()
        login_page = _fetch_text(opener=opener, url=login_url, timeout=30)
        csrf_token = _extract_csrf_token(login_page)
        if not csrf_token:
            raise CommandError("Could not extract CSRF token from cloud login page.")

        _post_form(
            opener=opener,
            url=login_url,
            referer=login_url,
            form_data={
                "csrfmiddlewaretoken": csrf_token,
                "username": username,
                "password": password,
            },
            timeout=30,
        )

        list_page = _fetch_text(opener=opener, url=activation_url, timeout=30)
        if "No active exams are scheduled for this day." in list_page and "No closed exams found" in list_page:
            self.stdout.write(self.style.WARNING("Cloud activation board returned no active or closed exams."))

        rows = _parse_list_page(list_page)
        if not rows:
            raise CommandError("Could not parse any exam rows from the cloud IT activation page.")

        pending_exam_ids = sorted(
            {
                int(row.payload.get("exam_id"))
                for row in SyncQueue.objects.filter(
                    status=SyncQueueStatus.RETRY,
                    operation_type=SyncOperationType.CBT_EXAM_ATTEMPT,
                )
            }
        )
        for exam_id in pending_exam_ids:
            rows.setdefault(exam_id, CloudExamRow(exam_id=exam_id))

        for exam_id, exam_row in sorted(rows.items()):
            detail_url = urllib.parse.urljoin(activation_url, f"{exam_id}/")
            try:
                detail_page = _fetch_text(opener=opener, url=detail_url, timeout=30)
            except urllib.error.HTTPError as exc:
                if int(getattr(exc, "code", 0) or 0) == 404:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Cloud detail page missing for exam {exam_id}; keeping any list metadata only."
                        )
                    )
                    continue
                raise
            rows[exam_id] = _parse_detail_page(page_html=detail_page, exam_row=exam_row)

        self.stdout.write(f"Recovered cloud metadata for {len(rows)} exam(s).")

        if dry_run:
            missing = [exam_id for exam_id in pending_exam_ids if exam_id not in rows]
            self.stdout.write(f"Attempt retry exam ids: {len(pending_exam_ids)}")
            self.stdout.write(f"Missing from scraped cloud catalog: {missing}")
            return

        setup_state = SystemSetupState.get_solo()
        fallback_actor = (
            User.objects.filter(username__iexact=username).first()
            or User.objects.filter(username__iexact="principal@ndgakuje.org").first()
            or User.objects.filter(is_superuser=True).order_by("id").first()
        )

        created_count = 0
        updated_count = 0
        skipped_ids: list[int] = []

        with suppress_cbt_change_capture():
            for exam_id, row in sorted(rows.items()):
                try:
                    context = _resolve_required_exam_context(
                        row=row,
                        fallback_actor=fallback_actor,
                        setup_state=setup_state,
                    )
                except CommandError as exc:
                    skipped_ids.append(exam_id)
                    self.stdout.write(self.style.WARNING(str(exc)))
                    continue

                exam_type_value = EXAM_TYPE_VALUE_BY_LABEL.get(
                    (row.exam_type_label or "CA").strip().lower(),
                    CBTExamType.CA,
                )
                status_value = STATUS_VALUE_BY_LABEL.get(
                    (row.status_label or "Closed").strip().lower(),
                    CBTExamStatus.CLOSED,
                )

                defaults = {
                    "title": row.title or f"Recovered Cloud Exam {exam_id}",
                    "description": "",
                    "exam_type": exam_type_value,
                    "status": status_value,
                    "created_by": context["created_by"],
                    "assignment": context["assignment"],
                    "subject": context["subject"],
                    "academic_class": context["academic_class"],
                    "session": context["session"],
                    "term": context["term"],
                    "question_bank": None,
                    "dean_reviewed_by": context["dean_reviewed_by"],
                    "dean_reviewed_at": None,
                    "dean_review_comment": "",
                    "activated_by": context["activated_by"],
                    "activated_at": None,
                    "activation_comment": "",
                    "schedule_start": _parse_exam_datetime(row.schedule_start),
                    "schedule_end": _parse_exam_datetime(row.schedule_end),
                    "is_time_based": bool(row.is_time_based),
                    "open_now": bool(row.open_now),
                    "is_free_test": exam_type_value == CBTExamType.FREE_TEST,
                }

                existed = Exam.objects.filter(pk=exam_id).exists()
                exam, _ = Exam.objects.update_or_create(pk=exam_id, defaults=defaults)
                if existed:
                    updated_count += 1
                else:
                    created_count += 1

                blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
                blueprint.duration_minutes = max(int(row.duration_minutes or 60), 1)
                blueprint.max_attempts = max(int(row.max_attempts or 1), 1)
                blueprint.shuffle_questions = bool(row.shuffle_questions)
                blueprint.shuffle_options = bool(row.shuffle_options)
                blueprint.instructions = row.instructions
                blueprint.save(
                    update_fields=[
                        "duration_minutes",
                        "max_attempts",
                        "shuffle_questions",
                        "shuffle_options",
                        "instructions",
                        "updated_at",
                    ]
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Recovered local exam catalog: created {created_count}, updated {updated_count}, skipped {len(skipped_ids)}."
            )
        )

        missing_exam_ids = [exam_id for exam_id in pending_exam_ids if not Exam.objects.filter(pk=exam_id).exists()]
        if missing_exam_ids:
            self.stdout.write(
                self.style.WARNING(
                    f"Attempt retry rows still reference missing exam ids: {missing_exam_ids}"
                )
            )

        if skip_retry_replay:
            return

        replay_summary = {"applied": 0, "duplicates": 0, "blocked": 0}
        retry_rows = SyncQueue.objects.filter(
            status=SyncQueueStatus.RETRY,
            operation_type=SyncOperationType.CBT_EXAM_ATTEMPT,
        ).order_by("id")
        for row in retry_rows:
            envelope = {
                "payload": row.payload,
                "operation_type": row.operation_type,
                "idempotency_key": row.idempotency_key,
                "object_ref": row.object_ref,
                "conflict_rule": row.conflict_rule,
                "conflict_key": row.conflict_key,
                "local_node_id": row.local_node_id,
            }
            try:
                result = ingest_remote_outbox_event(envelope=envelope)
            except ValidationError:
                replay_summary["blocked"] += 1
                continue
            if result.get("status") == "duplicate":
                replay_summary["duplicates"] += 1
            else:
                replay_summary["applied"] += 1

        self.stdout.write(
            self.style.SUCCESS(
                "CBT attempt retry replay complete: "
                f"applied {replay_summary['applied']}, "
                f"duplicates {replay_summary['duplicates']}, "
                f"blocked {replay_summary['blocked']}."
            )
        )
