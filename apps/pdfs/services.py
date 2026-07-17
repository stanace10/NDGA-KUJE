import base64
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db.models import Avg, Count, Max, Min, Model, Q, Sum
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import (
    AcademicSession,
    GradeScale,
    StudentClassEnrollment,
    TeacherSubjectAssignment,
)
from apps.academics.grade_scale import grade_metadata_for_grade, grade_metadata_for_score, is_failing_grade, remark_for_score
from apps.academics.subject_policy import NON_RESULT_SUBJECT_NAMES, exclude_non_result_subjects
from apps.accounts.constants import (
    ROLE_BURSAR,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
)
from apps.accounts.models import User
from apps.dashboard.models import PrincipalSignature, SchoolProfile
from apps.elections.models import Candidate, ElectionStatus, Vote
from apps.attendance.services import compute_student_attendance_percentage, get_student_attendance_snapshot_for_window
from apps.finance.models import FinanceInstitutionProfile
from apps.pdfs.models import PDFArtifact, PDFDocumentType, TranscriptSessionRecord
from apps.results.models import (
    BehaviorMetricSetting,
    ClassCompilationStatus,
    ClassResultCompilation,
    ClassResultStudentRecord,
    ResultSheet,
    ResultSheetStatus,
    ResultSubmission,
    StudentSubjectScore,
)
from apps.results.insights import build_result_comment_bundle
from apps.results.annual_subjects import annual_subject_label, build_annual_subject_slots
from apps.tenancy.utils import build_portal_url


TERM_ORDER = {"FIRST": 1, "SECOND": 2, "THIRD": 3}
DEFAULT_BEHAVIOR_LABELS = {
    "punctuality": "Punctuality",
    "neatness": "Neatness",
    "politeness": "Politeness",
    "honesty": "Honesty",
    "attentiveness": "Attentiveness",
    "relationship": "Relationship With Others",
    "self_control": "Self Control",
    "perseverance": "Perseverance",
    "leadership": "Leadership",
    "participation": "Class Participation",
}
STAFF_REPORT_DOWNLOAD_ROLES = {
    ROLE_IT_MANAGER,
    ROLE_VP,
    ROLE_PRINCIPAL,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_SUBJECT_TEACHER,
    ROLE_BURSAR,
}


def _uses_legacy_result_layout(term):
    return bool(term and term.name in {"FIRST", "SECOND"})


def _to_primitive(value):
    if isinstance(value, Decimal):
        return format(value, ".2f")
    if isinstance(value, Model):
        return str(value.pk) if getattr(value, "pk", None) is not None else str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _to_primitive(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_primitive(item) for item in value]
    return value


def payload_sha256(payload):
    canonical = json.dumps(_to_primitive(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_file_as_data_uri(path):
    if not path:
        return ""
    suffix = Path(path).suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")
    with open(path, "rb") as stream:
        encoded = base64.b64encode(stream.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _svg_data_uri(svg_markup):
    encoded = base64.b64encode(svg_markup.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def school_profile():
    return SchoolProfile.load()


def school_logo_data_uri():
    profile = SchoolProfile.objects.first()
    if profile and profile.school_logo:
        path = getattr(profile.school_logo, "path", "")
        if path and Path(path).exists():
            return _read_file_as_data_uri(path)
    logo_path = finders.find("images/ndga/logo.png")
    if logo_path:
        return _read_file_as_data_uri(logo_path)
    fallback_path = settings.ROOT_DIR / "static" / "images" / "ndga" / "logo.png"
    if fallback_path.exists():
        return _read_file_as_data_uri(fallback_path)
    return ""


def school_stamp_data_uri():
    profile = SchoolProfile.objects.first()
    if not profile or not profile.school_stamp:
        return fallback_school_stamp_data_uri(profile=profile)
    path = getattr(profile.school_stamp, "path", "")
    if not path or not Path(path).exists():
        return fallback_school_stamp_data_uri(profile=profile)
    return _read_file_as_data_uri(path)


def fallback_school_stamp_data_uri(*, profile=None):
    profile = profile or SchoolProfile.objects.first()
    school_name = getattr(profile, "school_name", "") or "Notre Dame Girls' Academy"
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="260" height="260" viewBox="0 0 260 260">
      <circle cx="130" cy="130" r="112" fill="none" stroke="#295b94" stroke-width="9"/>
      <circle cx="130" cy="130" r="88" fill="none" stroke="#c62828" stroke-width="4"/>
      <text x="130" y="96" text-anchor="middle" font-family="Georgia, serif" font-size="24" font-weight="700" fill="#295b94">NDGA</text>
      <text x="130" y="128" text-anchor="middle" font-family="Georgia, serif" font-size="13" font-weight="700" fill="#111111">{school_name[:28]}</text>
      <text x="130" y="154" text-anchor="middle" font-family="Georgia, serif" font-size="15" font-weight="700" fill="#c62828">OFFICIAL RESULT</text>
      <text x="130" y="181" text-anchor="middle" font-family="Georgia, serif" font-size="13" font-weight="700" fill="#111111">SCHOOL STAMP</text>
    </svg>
    """
    return _svg_data_uri(svg)


def principal_signature_data_uri(*, preferred_user=None):
    if preferred_user is not None:
        preferred_signature = getattr(preferred_user, "principal_signature", None)
        if preferred_signature and preferred_signature.signature_image:
            path = getattr(preferred_signature.signature_image, "path", "")
            if path and Path(path).exists():
                return _read_file_as_data_uri(path)

    signature = (
        PrincipalSignature.objects.filter(
            Q(user__primary_role__code=ROLE_PRINCIPAL)
            | Q(user__secondary_roles__code=ROLE_PRINCIPAL),
            signature_image__isnull=False,
        )
        .exclude(signature_image="")
        .select_related("user")
        .order_by("-updated_at")
        .distinct()
        .first()
    )
    if not signature or not signature.signature_image:
        fallback_path = settings.ROOT_DIR / "SCHOOL FOLDER" / "principal signature.png"
        if fallback_path.exists():
            return _read_file_as_data_uri(fallback_path)
        return fallback_principal_signature_data_uri()

    path = getattr(signature.signature_image, "path", "")
    if not path or not Path(path).exists():
        fallback_path = settings.ROOT_DIR / "SCHOOL FOLDER" / "principal signature.png"
        if fallback_path.exists():
            return _read_file_as_data_uri(fallback_path)
        return fallback_principal_signature_data_uri()
    return _read_file_as_data_uri(path)


def fallback_principal_signature_data_uri():
    profile = school_profile()
    name = (getattr(profile, "principal_name", "") or "Principal").strip()
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="420" height="120" viewBox="0 0 420 120">
      <path d="M24 78 C62 18, 92 20, 77 69 C68 99, 127 31, 145 54 C162 76, 181 72, 203 45 C194 91, 237 78, 261 51 C253 89, 304 76, 338 48 C357 32, 371 39, 397 31"
        fill="none" stroke="#111827" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
      <text x="210" y="108" text-anchor="middle" font-family="Georgia, serif" font-size="18" fill="#111827">{name}</text>
    </svg>
    """
    return _svg_data_uri(svg)


def student_profile_photo_data_uri(student):
    profile = getattr(student, "student_profile", None)
    if not profile or not getattr(profile, "profile_photo", None):
        return ""
    path = getattr(profile.profile_photo, "path", "")
    if not path or not Path(path).exists():
        return ""
    return _read_file_as_data_uri(path)


def qr_code_data_uri(raw_text):
    try:
        import qrcode
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "qrcode package is required for Stage 8 PDF verification. Install requirements/base.txt."
        ) from exc

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=7,
        border=2,
    )
    qr.add_data(raw_text)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def compute_age(date_of_birth, reference_date=None):
    if not date_of_birth:
        return None
    reference = reference_date or timezone.localdate()
    return reference.year - date_of_birth.year - (
        (reference.month, reference.day) < (date_of_birth.month, date_of_birth.day)
    )


def student_display_name(student):
    profile = getattr(student, "student_profile", None)
    parts = [student.last_name, student.first_name]
    if profile and profile.middle_name:
        parts.append(profile.middle_name)
    cleaned = [part for part in parts if part]
    if cleaned:
        return " ".join(cleaned)
    return student.get_full_name() or student.username


def get_grade_key_rows():
    rows = list(GradeScale.objects.filter(is_default=True).order_by("sort_order", "grade"))
    if not rows:
        GradeScale.ensure_default_scale()
        rows = list(GradeScale.objects.filter(is_default=True).order_by("sort_order", "grade"))
    return rows


def _grade_key_payload():
    payload = []
    color_hex = {
        "Gold": "#D6A21E",
        "Silver": "#6B7280",
        "Bronze": "#B45309",
        "Black": "#111111",
        "Green": "#008000",
        "Blue": "#1f5cff",
        "Orange": "#F97316",
        "Red": "#c62828",
    }
    for row in get_grade_key_rows():
        meta = grade_metadata_for_grade(row.grade)
        payload.append(
            {
                "grade": row.grade,
                "min_score": row.min_score,
                "max_score": row.max_score,
                "remark": meta["remark"],
                "color": meta["color"],
                "css_class": meta["css_class"],
                "hex_color": color_hex.get(meta["color"], "#111111"),
            }
        )
    return payload


def _grade_color_hex(color_name):
    return {
        "Gold": "#D6A21E",
        "Silver": "#6B7280",
        "Bronze": "#B45309",
        "Black": "#111111",
        "Green": "#008000",
        "Blue": "#1f5cff",
        "Orange": "#F97316",
        "Red": "#c62828",
    }.get(str(color_name or "").strip().title(), "#111111")


def _grade_display_payload(*, score=None, grade=None):
    meta = grade_metadata_for_grade(grade) if grade else grade_metadata_for_score(score)
    return {
        "grade": meta["grade"],
        "remark": meta["remark"],
        "color": meta["color"],
        "css_class": meta["css_class"],
        "hex_color": _grade_color_hex(meta["color"]),
    }


def get_student_record_for_compilation(*, student, compilation):
    return ClassResultStudentRecord.objects.filter(
        compilation=compilation,
        student=student,
    ).first()


def _term_order_key(compilation):
    return (
        compilation.session.name,
        TERM_ORDER.get(compilation.term.name, 99),
    )


def _format_decimal(number):
    value = Decimal(number or 0)
    return value.quantize(Decimal("0.01"))


def _instructional_class(academic_class):
    return academic_class.instructional_class if academic_class else None


FIXED_CLASS_SUBJECT_COUNTS = {
    "JS1": 16,
    "JS2": 17,
    "SS1": 14,
    "SS2": 13,
}

HISTORICAL_TERM_CLASS_SUBJECT_COUNTS = {
    ("2025/2026", "FIRST", "JS1"): 18,
}


def _fixed_subject_count_for_class(academic_class, *, session=None, term=None):
    if academic_class is None:
        return None
    instructional = _instructional_class(academic_class)
    code = (getattr(instructional, "code", "") or "").strip().upper()
    session_name = (getattr(session, "name", "") or "").strip()
    term_name = (getattr(term, "name", "") or "").strip().upper()
    historical_count = HISTORICAL_TERM_CLASS_SUBJECT_COUNTS.get((session_name, term_name, code))
    if historical_count:
        return historical_count
    return FIXED_CLASS_SUBJECT_COUNTS.get(code)


def _compilation_student_ids(compilation):
    student_ids = list(
        StudentClassEnrollment.objects.filter(
            academic_class=compilation.academic_class,
            session=compilation.session,
            is_active=True,
        ).values_list("student_id", flat=True)
    )
    if student_ids:
        return student_ids
    return list(compilation.student_records.values_list("student_id", flat=True))


def _ordinal(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "-"
    if 10 <= (number % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def _score_remark(total, grade):
    return remark_for_score(total, grade)


def _risk_label(*, average, attendance, fail_count):
    if attendance < 60 or fail_count >= 3 or average < 50:
        return "High"
    if attendance < 75 or fail_count >= 1 or average < 60:
        return "Moderate"
    return "Low"


def _behavior_metric_rows(record):
    breakdown = getattr(record, "behavior_breakdown", {}) or {}
    configured = list(
        BehaviorMetricSetting.objects.filter(is_active=True)
        .order_by("sort_order", "label")
        .values_list("code", "label")
    )
    if not configured:
        configured = list(DEFAULT_BEHAVIOR_LABELS.items())
    rows = []
    for code, label in configured:
        value = breakdown.get(code)
        rows.append({"code": code, "label": label, "value": value if value not in (None, "") else "-"})
    return rows


def _cognitive_domain_rows(subject_rows):
    if not subject_rows:
        return []

    def _average(values):
        if not values:
            return Decimal("0.00")
        return (sum(values, Decimal("0.00")) / Decimal(len(values))).quantize(Decimal("0.01"))

    ca_values = [
        (Decimal(row.get("ca1") or 0) + Decimal(row.get("ca2") or 0) + Decimal(row.get("ca3") or 0))
        for row in subject_rows
    ]
    assignment_values = [Decimal(row.get("assignment") or 0) * Decimal("10") for row in subject_rows]
    exam_values = [Decimal(row.get("exam") or 0) * Decimal("2") for row in subject_rows]
    total_values = [Decimal(row.get("total") or 0) for row in subject_rows]

    rows = [
        ("Knowledge Retention", (_average(ca_values) / Decimal("30")) * Decimal("100")),
        ("Project / Practical", _average(assignment_values)),
        ("Examination Technique", _average(exam_values)),
        ("Overall Academic Mastery", _average(total_values)),
    ]

    payload = []
    for label, raw_score in rows:
        score = Decimal(raw_score or 0).quantize(Decimal("0.01"))
        payload.append(
            {
                "label": label,
                "score": score,
                "rating": remark_for_score(score),
            }
        )
    return payload


def _office_held_from_latest_election(*, student, session=None):
    def _position_rank_titles(position_name):
        raw_name = " ".join(str(position_name or "").split())
        if " / " in raw_name:
            return [segment.strip() for segment in raw_name.split(" / ") if segment.strip()]
        return [raw_name] if raw_name else []

    candidate_qs = (
        Candidate.objects.filter(
            user=student,
            is_active=True,
            position__is_active=True,
            position__election__is_active=True,
            position__election__status__in=[ElectionStatus.CLOSED, ElectionStatus.ARCHIVED],
        )
        .select_related("position", "position__election")
        .order_by("-position__election__closed_at", "-position__election__updated_at", "position__sort_order")
    )
    if session is not None:
        candidate_qs = candidate_qs.filter(position__election__session=session)

    offices = []
    seen = set()
    for candidate in candidate_qs:
        position = candidate.position
        ranked_candidates = list(
            position.candidates.filter(is_active=True)
            .annotate(vote_count=Count("votes"))
            .order_by("-vote_count", "user__username")
        )
        if not ranked_candidates:
            continue
        rank_titles = _position_rank_titles(position.name)
        for index, ranked_candidate in enumerate(ranked_candidates):
            if ranked_candidate.id != candidate.id:
                continue
            vote_count = Vote.objects.filter(
                election=position.election,
                position=position,
                candidate=candidate,
            ).count()
            if vote_count <= 0:
                break
            if index >= len(rank_titles):
                break
            title = rank_titles[index] or position.name
            key = (position.election_id, title)
            if key not in seen:
                offices.append(title)
                seen.add(key)
            break
        if offices:
            break
    return ", ".join(offices)


def _class_position_summary(*, compilation, target_student_id):
    student_ids = _compilation_student_ids(compilation)
    if not student_ids:
        return {"position": None, "class_average": Decimal("0.00"), "class_size": 0}
    score_queryset = StudentSubjectScore.objects.filter(
            result_sheet__academic_class=_instructional_class(compilation.academic_class),
            result_sheet__session=compilation.session,
            result_sheet__term=compilation.term,
            student_id__in=student_ids,
        )
    score_queryset = exclude_non_result_subjects(score_queryset, field_name="result_sheet__subject")
    score_rows = list(
        score_queryset
        .values("student_id")
        .annotate(total=Sum("grand_total"), subject_count=Count("id"))
    )
    ranking_rows = []
    for row in score_rows:
        actual_subject_count = int(row.get("subject_count") or 0)
        subject_count = actual_subject_count
        total = Decimal(row.get("total") or 0)
        average = (total / Decimal(subject_count)).quantize(Decimal("0.01")) if subject_count else Decimal("0.00")
        ranking_rows.append(
            {
                "student_id": row["student_id"],
                "total": total.quantize(Decimal("0.01")),
                "average": average,
            }
        )
    ranking_rows.sort(key=lambda row: (-row["average"], -row["total"], row["student_id"]))
    current_rank = None
    previous_key = None
    previous_rank = 0
    for index, row in enumerate(ranking_rows, start=1):
        current_key = (row["average"], row["total"])
        if current_key != previous_key:
            previous_rank = index
            previous_key = current_key
        if row["student_id"] == target_student_id:
            current_rank = previous_rank
            break
    class_average = Decimal("0.00")
    if ranking_rows:
        class_average = (
            sum((row["average"] for row in ranking_rows), Decimal("0.00")) / Decimal(len(ranking_rows))
        ).quantize(Decimal("0.01"))
    return {
        "position": current_rank,
        "class_average": class_average,
        "class_size": len(ranking_rows),
    }


def _subject_rows_for_compilation(*, student, compilation, published_only=True):
    legacy_layout = _uses_legacy_result_layout(compilation.term)
    instructional_class = _instructional_class(compilation.academic_class)
    sheet_queryset = ResultSheet.objects.filter(
        academic_class=instructional_class,
        session=compilation.session,
        term=compilation.term,
    )
    if published_only:
        sheet_queryset = sheet_queryset.filter(status=ResultSheetStatus.PUBLISHED)
    else:
        sheet_queryset = sheet_queryset.exclude(
            status__in=[
                ResultSheetStatus.DRAFT,
                ResultSheetStatus.REJECTED_BY_DEAN,
                ResultSheetStatus.REJECTED_BY_VP,
            ]
        )
    sheet_queryset = exclude_non_result_subjects(sheet_queryset, field_name="subject")
    sheets = list(
        sheet_queryset
        .select_related("subject")
        .order_by("subject__name")
    )
    peer_student_ids = _compilation_student_ids(compilation)
    score_rows = list(
        StudentSubjectScore.objects.filter(
            result_sheet__in=sheets,
            student_id__in=peer_student_ids,
        )
        .select_related("result_sheet", "result_sheet__subject")
        .order_by("result_sheet_id", "-grand_total", "student__last_name", "student__first_name", "student__username")
    )
    target_scores = {
        score.result_sheet_id: score
        for score in score_rows
        if score.student_id == student.id
    }
    grouped_scores = {}
    for score in score_rows:
        grouped_scores.setdefault(score.result_sheet_id, []).append(score)

    rows = []
    for sheet in sheets:
        score = target_scores.get(sheet.id)
        if not score or (legacy_layout and not _score_has_any_value(score)):
            continue
        peer_scores = grouped_scores.get(sheet.id, [])
        if legacy_layout:
            peer_scores = [peer for peer in peer_scores if _score_has_any_value(peer)]
        totals = [Decimal(row.grand_total or 0) for row in peer_scores]
        subject_position = None
        last_total = None
        last_rank = 0
        for index, peer in enumerate(peer_scores, start=1):
            peer_total = Decimal(peer.grand_total or 0)
            if last_total is None or peer_total < last_total:
                last_rank = index
                last_total = peer_total
            if peer.student_id == student.id:
                subject_position = last_rank
                break
        exam_component_total = Decimal(score.total_exam or 0) if legacy_layout else Decimal(score.objective or 0) + Decimal(score.theory or 0)
        average_total = (sum(totals, Decimal("0.00")) / Decimal(len(totals))).quantize(Decimal("0.01")) if totals else Decimal("0.00")
        row_total = _format_decimal(score.grand_total)
        grade_meta = _grade_display_payload(score=row_total, grade=score.grade)
        rows.append(
            {
                "result_sheet": score.result_sheet,
                "subject": sheet.subject.name,
                "use_legacy_result_layout": legacy_layout,
                "ca1": _format_decimal(score.ca1),
                "ca2": _format_decimal(score.ca2),
                "ca3": _format_decimal(score.ca3),
                "assignment": _format_decimal(score.ca4),
                "ca4": _format_decimal(score.ca4),
                "class_participation": _format_decimal(score.class_participation),
                "objective": _format_decimal(score.objective),
                "theory": _format_decimal(score.theory),
                "exam": _format_decimal(exam_component_total),
                "total": row_total,
                "grade": grade_meta["grade"],
                "remark": grade_meta["remark"],
                "grade_color": grade_meta["color"],
                "grade_css_class": grade_meta["css_class"],
                "grade_hex_color": grade_meta["hex_color"],
                "position": _ordinal(subject_position) if subject_position else "-",
                "highest": max(totals).quantize(Decimal("0.01")) if totals else Decimal("0.00"),
                "lowest": min(totals).quantize(Decimal("0.01")) if totals else Decimal("0.00"),
                "average": average_total,
            }
        )
    return rows


def _build_student_bio(*, student, compilation):
    profile = getattr(student, "student_profile", None)
    enrollment = StudentClassEnrollment.objects.filter(
        student=student,
        session=compilation.session,
        is_active=True,
    ).select_related("academic_class", "academic_class__base_class").first()
    academic_class = enrollment.academic_class if enrollment else compilation.academic_class
    class_level = academic_class.instructional_class if academic_class else compilation.academic_class.instructional_class
    return {
        "name": student_display_name(student),
        "student_number": profile.student_number if profile else student.username,
        "class_code": (academic_class.display_name or academic_class.code) if academic_class else (compilation.academic_class.display_name or compilation.academic_class.code),
        "class_level": class_level.display_name or class_level.code,
        "date_of_birth": profile.date_of_birth if profile else None,
        "age": compute_age(profile.date_of_birth if profile else None),
        "sex": profile.get_gender_display() if profile and profile.gender else "",
        "admission_date": profile.admission_date if profile else None,
        "house": (getattr(profile, "house", "") or "").strip() if profile else "",
        "community": (getattr(profile, "community", "") or "").strip() if profile else "",
        "society": (getattr(profile, "society", "") or "").strip() if profile else "",
    }


def _approval_trail(*, compilation):
    sheet_ids = list(
        ResultSheet.objects.filter(
            academic_class=_instructional_class(compilation.academic_class),
            session=compilation.session,
            term=compilation.term,
        ).values_list("id", flat=True)
    )
    if not sheet_ids:
        return []
    submissions = (
        ResultSubmission.objects.filter(result_sheet_id__in=sheet_ids)
        .select_related("actor", "result_sheet", "result_sheet__subject")
        .order_by("created_at")
    )
    markers = []
    for row in submissions:
        markers.append(
            {
                "subject": row.result_sheet.subject.code,
                "action": row.action,
                "from": row.from_status,
                "to": row.to_status,
                "actor": row.actor.username if row.actor else "",
                "at": row.created_at.isoformat(),
            }
        )
    return markers


def _term_report_layout_config(subject_count):
    if subject_count <= 0:
        return {
            "layout_density_class": "normal-density",
            "subject_row_height_px": 18,
            "behavior_box_min_height_px": 68,
            "comment_box_min_height_px": 38,
            "club_box_min_height_px": 26,
            "principal_comment_min_height_px": 28,
            "signature_row_height_px": 28,
        }
    if subject_count <= 8:
        return {
            "layout_density_class": "expanded-density",
            "subject_row_height_px": 22,
            "behavior_box_min_height_px": 86,
            "comment_box_min_height_px": 48,
            "club_box_min_height_px": 30,
            "principal_comment_min_height_px": 34,
            "signature_row_height_px": 30,
        }
    if subject_count <= 12:
        return {
            "layout_density_class": "expanded-density",
            "subject_row_height_px": 18,
            "behavior_box_min_height_px": 76,
            "comment_box_min_height_px": 42,
            "club_box_min_height_px": 28,
            "principal_comment_min_height_px": 32,
            "signature_row_height_px": 28,
        }
    if subject_count <= 16:
        return {
            "layout_density_class": "normal-density",
            "subject_row_height_px": 15,
            "behavior_box_min_height_px": 68,
            "comment_box_min_height_px": 36,
            "club_box_min_height_px": 26,
            "principal_comment_min_height_px": 28,
            "signature_row_height_px": 26,
        }
    return {
        "layout_density_class": "compact-density",
        "subject_row_height_px": 13,
        "behavior_box_min_height_px": 58,
        "comment_box_min_height_px": 30,
        "club_box_min_height_px": 24,
        "principal_comment_min_height_px": 24,
        "signature_row_height_px": 24,
    }


TERM_REPORT_EXCLUDED_SUBJECT_NAMES = NON_RESULT_SUBJECT_NAMES


def build_term_report_payload(*, student, compilation):
    if compilation.status != ClassCompilationStatus.PUBLISHED:
        raise ValueError("Term report can be generated only for published class compilations.")

    subject_rows = [
        row
        for row in _subject_rows_for_compilation(student=student, compilation=compilation)
        if str(row.get("subject") or "").strip().upper() not in TERM_REPORT_EXCLUDED_SUBJECT_NAMES
    ]
    actual_subject_count = len(subject_rows)
    subject_count = actual_subject_count
    cumulative_total = sum((row["total"] for row in subject_rows), Decimal("0.00"))
    average = Decimal("0.00")
    if subject_count:
        average = (cumulative_total / Decimal(subject_count)).quantize(Decimal("0.01"))

    record = get_student_record_for_compilation(student=student, compilation=compilation)
    attendance_snapshot = get_student_attendance_snapshot_for_window(
        student,
        session=compilation.session,
        term=compilation.term,
    )
    attendance_percentage = _format_decimal(record.attendance_percentage if record else 0)
    if attendance_snapshot:
        attendance_percentage = _format_decimal(attendance_snapshot.get("percentage") or attendance_percentage)
    elif not attendance_percentage and compilation.term_id:
        enrollment = StudentClassEnrollment.objects.filter(
            student=student,
            session=compilation.session,
            is_active=True,
        ).select_related("academic_class").first()
        if enrollment and hasattr(compilation.term, "school_calendar"):
            attendance_percentage = compute_student_attendance_percentage(
                student=student,
                calendar=compilation.term.school_calendar,
                academic_class=enrollment.academic_class,
            )

    position_summary = _class_position_summary(compilation=compilation, target_student_id=student.id)
    fail_count = len([row for row in subject_rows if is_failing_grade(row.get("grade"))])
    weak_subjects = [row["subject"] for row in subject_rows if Decimal(row["total"] or 0) < Decimal("60")][:3]
    profile = school_profile()
    comment_bundle = build_result_comment_bundle(
        student_name=student_display_name(student),
        average_score=average,
        attendance_percentage=attendance_percentage,
        fail_count=fail_count,
        weak_subjects=weak_subjects,
        predicted_score=average,
        risk_label=_risk_label(average=float(average), attendance=float(attendance_percentage), fail_count=fail_count),
        teacher_guidance=profile.teacher_comment_guidance or profile.auto_comment_guidance,
        dean_guidance=profile.dean_comment_guidance or profile.auto_comment_guidance,
        principal_guidance=profile.principal_comment_guidance or profile.auto_comment_guidance,
    )
    principal_comment = (
        (getattr(record, "principal_comment", "") or "").strip()
        or (compilation.decision_comment or "").strip()
        or comment_bundle["principal_comment"]
    )

    school_days = int(attendance_snapshot.get("valid_school_days", 0) or 0) if attendance_snapshot else 0
    present_days = int(attendance_snapshot.get("present_days", 0) or 0) if attendance_snapshot else 0
    absent_days = int(attendance_snapshot.get("absent_days", 0) or 0) if attendance_snapshot else 0
    behavior_rows = _behavior_metric_rows(record) if record else []
    office_held = (getattr(record, "office_held", "") or "").strip() if record else ""
    if not office_held:
        office_held = _office_held_from_latest_election(student=student, session=compilation.session)
    if not office_held:
        office_held = _office_held_from_latest_election(student=student)
    class_code = compilation.academic_class.display_name or compilation.academic_class.code
    level_code = compilation.academic_class.instructional_class.display_name or compilation.academic_class.instructional_class.code
    layout = _term_report_layout_config(subject_count)
    return {
        "document_type": PDFDocumentType.TERM_REPORT,
        "student_id": student.id,
        "student_bio": _build_student_bio(student=student, compilation=compilation),
        "session_name": compilation.session.name,
        "term_name": compilation.term.get_name_display(),
        "use_legacy_result_layout": _uses_legacy_result_layout(compilation.term),
        "class_code": class_code,
        "class_level": level_code,
        "published_at": compilation.published_at or compilation.updated_at,
        "attendance_percentage": attendance_percentage,
        "attendance": {
            "school_open": school_days,
            "present": present_days,
            "absent": absent_days,
        },
        "behavior_rating": record.behavior_rating if record else 3,
        "behavior_rows": behavior_rows,
        "cognitive_rows": _cognitive_domain_rows(subject_rows),
        "teacher_comment": record.teacher_comment if record else "",
        "hostel_supervisor_comment": getattr(record, "hostel_supervisor_comment", "") if record else "",
        "parent_comment": getattr(record, "parent_comment", "") if record else "",
        "dean_comment": comment_bundle["dean_comment"],
        "principal_comment": principal_comment,
        "comment_headline": comment_bundle["headline"],
        "subject_rows": subject_rows,
        "subject_count": subject_count,
        "actual_subject_count": actual_subject_count,
        **layout,
        "total_mark_obtainable": subject_count * 100,
        "cumulative_total": cumulative_total.quantize(Decimal("0.01")),
        "average": average,
        "class_average": position_summary["class_average"],
        "class_position": _ordinal(position_summary["position"]) if position_summary["position"] else "-",
        "class_size": position_summary["class_size"],
        "grade_key": _grade_key_payload(),
        "term_weight_kg": getattr(record, "term_weight_kg", None) if record else None,
        "health": {
            "height_start_cm": getattr(record, "height_start_cm", None) if record else None,
            "height_end_cm": getattr(record, "height_end_cm", None) if record else None,
            "weight_start_kg": getattr(record, "weight_start_kg", None) if record else None,
            "weight_end_kg": getattr(record, "weight_end_kg", None) if record else None,
            "medical_incidents": getattr(record, "medical_incidents", 0) if record else 0,
            "nature_of_illness": "",
            "doctor_remark": getattr(record, "doctor_remark", "") if record else "",
        },
        "co_curricular": {
            "club_membership": getattr(record, "club_membership", "") if record else "",
            "office_held": office_held,
            "notable_contribution": getattr(record, "notable_contribution", "") if record else "",
        },
        "approval_trail": _approval_trail(compilation=compilation),
        "compilation_id": compilation.id,
    }


def _published_session_compilations_for_student(*, student, session, academic_class):
    return {
        row.term.name: row
        for row in ClassResultCompilation.objects.filter(
            session=session,
            academic_class=academic_class,
            status=ClassCompilationStatus.PUBLISHED,
            student_records__student=student,
        )
        .select_related("academic_class", "session", "term")
        .distinct()
    }


def _annual_subject_label(subject_name):
    return annual_subject_label(subject_name)


def _annual_term_average(rows):
    values = [
        Decimal(row.get("total"))
        for row in rows
        if row.get("total") not in (None, "")
    ]
    if not values:
        return None
    return (sum(values, Decimal("0.00")) / Decimal(len(values))).quantize(Decimal("0.01"))


def _score_has_any_value(score):
    if score is None:
        return False
    fields = ("ca1", "ca2", "ca3", "ca4", "class_participation", "objective", "theory")
    return any(Decimal(getattr(score, field, 0) or 0) > Decimal("0.00") for field in fields)


def _pure_annual_average_from_compilations_raw(*, student, compilations):
    """Average exact term averages instead of pooling uneven term totals."""

    term_averages = []
    for term_key in ("FIRST", "SECOND", "THIRD"):
        compilation = compilations.get(term_key)
        if not compilation:
            continue
        rows = _subject_rows_for_compilation(student=student, compilation=compilation, published_only=False)
        values = [
            Decimal(row.get("total"))
            for row in rows
            if row.get("total") not in (None, "")
        ]
        if values:
            term_averages.append(sum(values, Decimal("0.00")) / Decimal(len(values)))
    if not term_averages:
        return None
    return sum(term_averages, Decimal("0.00")) / Decimal(len(term_averages))


def _pure_annual_average_from_compilations(*, student, compilations):
    raw_average = _pure_annual_average_from_compilations_raw(student=student, compilations=compilations)
    if raw_average is None:
        return None
    return raw_average.quantize(Decimal("0.01"))


def _annual_subject_rows_for_student(*, student, session, academic_class, current_compilation=None):
    compilations = _published_session_compilations_for_student(
        student=student,
        session=session,
        academic_class=academic_class,
    )
    if current_compilation is not None and current_compilation.session_id == session.id:
        compilations[current_compilation.term.name] = current_compilation
    term_subject_rows = {}
    for term_key in ("FIRST", "SECOND", "THIRD"):
        compilation = compilations.get(term_key)
        if not compilation:
            continue
        for row in _subject_rows_for_compilation(student=student, compilation=compilation, published_only=False):
            subject = str(row.get("subject") or "").strip()
            if not subject:
                continue
            term_subject_rows.setdefault(term_key, []).append((subject, row))

    term_rows_by_subject, _diagnostics = build_annual_subject_slots(term_subject_rows, student=student)

    subject_rows = []
    for subject in sorted(term_rows_by_subject):
        term_map = term_rows_by_subject[subject]
        first = _annual_term_average(term_map.get("FIRST", []))
        second = _annual_term_average(term_map.get("SECOND", []))
        third = _annual_term_average(term_map.get("THIRD", []))
        numeric_values = [value for value in (first, second, third) if value is not None]
        term_count = len(numeric_values)
        total_300 = sum(numeric_values, Decimal("0.00")).quantize(Decimal("0.01"))
        average = None
        grade_meta = None
        if term_count:
            average = (total_300 / Decimal(term_count)).quantize(Decimal("0.01"))
            grade_meta = _grade_display_payload(score=average)
        else:
            grade_meta = {
                "grade": "-",
                "remark": "Pending",
                "color": "Black",
                "css_class": "legend-dark",
                "hex_color": "#111111",
            }
        subject_rows.append(
            {
                "subject": subject,
                "first_term": _format_decimal(first) if first not in (None, "") else None,
                "second_term": _format_decimal(second) if second not in (None, "") else None,
                "third_term": _format_decimal(third) if third not in (None, "") else None,
                "total_300": total_300 if average is not None else None,
                "term_count": term_count,
                "obtainable": term_count * 100,
                "average": average,
                "grade": grade_meta["grade"],
                "remark": grade_meta["remark"],
                "grade_color": grade_meta["color"],
                "grade_css_class": grade_meta["css_class"],
                "grade_hex_color": grade_meta["hex_color"],
                "is_complete": average is not None,
                "position": "-",
                "highest": None,
                "lowest": None,
                "class_average": None,
            }
        )
    return subject_rows, compilations


def _annual_subject_statistics(*, session, academic_class, subject):
    student_ids = list(
        StudentClassEnrollment.objects.filter(
            academic_class=academic_class,
            session=session,
            is_active=True,
        ).values_list("student_id", flat=True)
    )
    if not student_ids:
        student_ids = list(
            ClassResultStudentRecord.objects.filter(
                compilation__session=session,
                compilation__academic_class=academic_class,
            )
            .values_list("student_id", flat=True)
            .distinct()
        )
    rows = []
    required_terms = set()
    for candidate in User.objects.filter(id__in=student_ids).order_by("id"):
        candidate_rows, _compilations = _annual_subject_rows_for_student(
            student=candidate,
            session=session,
            academic_class=academic_class,
        )
        match = next((row for row in candidate_rows if row.get("subject") == subject), None)
        if match and match.get("average") is not None:
            candidate_terms = {
                term_name
                for term_name, field_name in (
                    ("FIRST", "first_term"),
                    ("SECOND", "second_term"),
                    ("THIRD", "third_term"),
                )
                if match.get(field_name) not in (None, "")
            }
            required_terms.update(candidate_terms)
            rows.append(
                {
                    "student_id": candidate.id,
                    "average": Decimal(match["average"]),
                    "candidate_terms": candidate_terms,
                }
            )
    if len(required_terms) < 2:
        rows = []
    else:
        rows = [
            row
            for row in rows
            if required_terms.issubset(row["candidate_terms"])
        ]
    rows.sort(key=lambda item: (-item["average"], item["student_id"]))
    if not rows:
        return {"position_by_student": {}, "highest": None, "lowest": None, "class_average": None}
    position_by_student = {}
    previous_average = None
    rank = 0
    for index, row in enumerate(rows, start=1):
        if previous_average is None or row["average"] < previous_average:
            rank = index
            previous_average = row["average"]
        position_by_student[row["student_id"]] = rank
    values = [row["average"] for row in rows]
    return {
        "position_by_student": position_by_student,
        "highest": max(values).quantize(Decimal("0.01")),
        "lowest": min(values).quantize(Decimal("0.01")),
        "class_average": (sum(values, Decimal("0.00")) / Decimal(len(values))).quantize(Decimal("0.01")),
    }


def _apply_annual_subject_statistics(*, rows, student, session, academic_class):
    for row in rows:
        if row.get("average") is None:
            continue
        stats = _annual_subject_statistics(
            session=session,
            academic_class=academic_class,
            subject=row["subject"],
        )
        position = stats["position_by_student"].get(student.id)
        row["position"] = _ordinal(position) if position else "-"
        row["highest"] = stats["highest"]
        row["lowest"] = stats["lowest"]
        row["class_average"] = stats["class_average"]
    return rows


def _annual_average_for_student(*, student, session, academic_class):
    rows, compilations = _annual_subject_rows_for_student(
        student=student,
        session=session,
        academic_class=academic_class,
    )
    if "THIRD" not in compilations:
        return None
    return _pure_annual_average_from_compilations(student=student, compilations=compilations)


def _annual_ranking_average_for_student(*, student, session, academic_class):
    rows, compilations = _annual_subject_rows_for_student(
        student=student,
        session=session,
        academic_class=academic_class,
    )
    if "THIRD" not in compilations:
        return None
    return _pure_annual_average_from_compilations_raw(student=student, compilations=compilations)


def _annual_position_summary(*, student, session, academic_class):
    student_ids = list(
        ClassResultStudentRecord.objects.filter(
            compilation__session=session,
            compilation__academic_class=academic_class,
        )
        .values_list("student_id", flat=True)
        .distinct()
    )
    rows = []
    for candidate in User.objects.filter(id__in=student_ids):
        average = _annual_ranking_average_for_student(
            student=candidate,
            session=session,
            academic_class=academic_class,
        )
        if average is not None:
            rows.append({"student_id": candidate.id, "average": average})
    rows.sort(key=lambda item: (-item["average"], item["student_id"]))
    class_average = Decimal("0.00")
    if rows:
        class_average = (sum((row["average"] for row in rows), Decimal("0.00")) / Decimal(len(rows))).quantize(Decimal("0.01"))
    position = None
    previous_average = None
    rank = 0
    for index, row in enumerate(rows, start=1):
        if previous_average is None or row["average"] < previous_average:
            rank = index
            previous_average = row["average"]
        if row["student_id"] == student.id:
            position = rank
            break
    return {
        "position": position,
        "class_size": len(rows),
        "class_average": class_average,
    }


def build_cumulative_report_payload(*, student, compilation):
    session = compilation.session
    academic_class = compilation.academic_class
    subject_rows, compilations = _annual_subject_rows_for_student(
        student=student,
        session=session,
        academic_class=academic_class,
        current_compilation=compilation,
    )
    subject_rows = _apply_annual_subject_statistics(
        rows=subject_rows,
        student=student,
        session=session,
        academic_class=academic_class,
    )
    available_terms = set(compilations)
    missing_terms = [label for key, label in (("FIRST", "First Term"), ("SECOND", "Second Term"), ("THIRD", "Third Term")) if key not in available_terms]
    complete_rows = [row for row in subject_rows if row.get("average") is not None]
    actual_subject_count = len(complete_rows)
    subject_count = actual_subject_count
    total_300 = sum((Decimal(row["total_300"]) for row in complete_rows), Decimal("0.00")).quantize(Decimal("0.01")) if complete_rows else Decimal("0.00")
    total_obtainable = sum((int(row.get("obtainable") or 0) for row in complete_rows), 0)
    annual_average = Decimal("0.00")
    pure_annual_average = _pure_annual_average_from_compilations(student=student, compilations=compilations)
    if pure_annual_average is not None:
        annual_average = pure_annual_average
    elif complete_rows and subject_count:
        annual_average = (sum((Decimal(row["average"]) for row in complete_rows), Decimal("0.00")) / Decimal(subject_count)).quantize(Decimal("0.01"))
    grade_meta = _grade_display_payload(score=annual_average)
    is_complete = "THIRD" in available_terms and bool(complete_rows)
    promotion_status = "Pending"
    promotion_note = "Awaiting Third Term result for annual promotion."
    if is_complete:
        promotion_status = "Promoted" if annual_average >= Decimal("50.00") else "Not Promoted"
        promotion_note = "Based on available term scores for current Third Term subjects."
    position_summary = _annual_position_summary(student=student, session=session, academic_class=academic_class)
    profile = school_profile()
    record = get_student_record_for_compilation(student=student, compilation=compilation)
    office_held = (getattr(record, "office_held", "") or "").strip() if record else ""
    if not office_held:
        office_held = _office_held_from_latest_election(student=student, session=session)
    if not office_held:
        office_held = _office_held_from_latest_election(student=student)
    student_bio = _build_student_bio(student=student, compilation=compilation)
    class_level_label = academic_class.instructional_class.display_name or academic_class.instructional_class.code
    section_title = "CUMULATIVE REPORT"
    return {
        "document_type": PDFDocumentType.CUMULATIVE_REPORT,
        "student_id": student.id,
        "student_bio": student_bio,
        "session_name": session.name,
        "class_code": academic_class.display_name or academic_class.code,
        "class_level": class_level_label,
        "section_title": section_title,
        "term_name": "Annual",
        "published_at": compilation.published_at or compilation.updated_at or timezone.now(),
        "subject_rows": subject_rows,
        "subject_count": subject_count,
        "actual_subject_count": actual_subject_count,
        "missing_terms": missing_terms,
        "is_complete": is_complete,
        "total_300": total_300,
        "total_mark_obtainable": total_obtainable,
        "annual_average": annual_average,
        "grade": grade_meta["grade"],
        "remark": grade_meta["remark"],
        "grade_color": grade_meta["color"],
        "grade_css_class": grade_meta["css_class"],
        "grade_hex_color": grade_meta["hex_color"],
        "class_position": _ordinal(position_summary["position"]) if position_summary["position"] else "-",
        "class_size": position_summary["class_size"],
        "class_average": position_summary["class_average"],
        "promotion_status": promotion_status,
        "promotion_note": promotion_note,
        "grade_key": _grade_key_payload(),
        "term_status": {
            "first": "Available" if "FIRST" in available_terms else "Pending Import",
            "second": "Available" if "SECOND" in available_terms else "Pending Import",
            "third": "Available" if "THIRD" in available_terms else "Pending Import",
        },
        "attendance_percentage": getattr(record, "attendance_percentage", Decimal("100.00")) if record else Decimal("100.00"),
        "attendance": {
            "school_open": getattr(record, "school_open", 0) if record else 0,
            "present": getattr(record, "present_days", 0) if record else 0,
            "absent": getattr(record, "absent_days", 0) if record else 0,
        },
        "behavior_rating": record.behavior_rating if record else 3,
        "behavior_rows": _behavior_metric_rows(record) if record else [],
        "teacher_comment": getattr(record, "teacher_comment", "") if record else "",
        "principal_comment": (
            (getattr(record, "principal_comment", "") or "").strip()
            or (getattr(compilation, "decision_comment", "") or "").strip()
            or profile.principal_comment_guidance
            or profile.auto_comment_guidance
        ),
        "co_curricular": {
            "office_held": office_held,
            "club_membership": getattr(record, "club_membership", "") if record else "",
            "notable_contribution": getattr(record, "notable_contribution", "") if record else "",
        },
        "compilation_id": compilation.id,
    }


def _transcript_compilations_for_student(student, *, session=None):
    qs = (
        ClassResultCompilation.objects.filter(
            status=ClassCompilationStatus.PUBLISHED,
            student_records__student=student,
        )
        .select_related("academic_class", "session", "term")
        .distinct()
    )
    if session is not None:
        qs = qs.filter(session=session)
    return sorted(qs, key=_term_order_key)


def _build_transcript_terms_from_compilations(*, student, compilations):
    terms = []
    all_subject_totals = []
    for compilation in compilations:
        subject_rows = _subject_rows_for_compilation(student=student, compilation=compilation)
        cumulative_total = sum((row["total"] for row in subject_rows), Decimal("0.00"))
        average = Decimal("0.00")
        if subject_rows:
            average = (cumulative_total / Decimal(len(subject_rows))).quantize(Decimal("0.01"))
        terms.append(
            {
                "session_name": compilation.session.name,
                "term_name": compilation.term.get_name_display(),
                "use_legacy_result_layout": _uses_legacy_result_layout(compilation.term),
                "class_code": compilation.academic_class.display_name or compilation.academic_class.code,
                "published_at": compilation.published_at or compilation.updated_at,
                "subject_rows": subject_rows,
                "subject_count": len(subject_rows),
                "cumulative_total": cumulative_total.quantize(Decimal("0.01")),
                "average": average,
                "compilation_id": compilation.id,
            }
        )
        all_subject_totals.extend(row["total"] for row in subject_rows)
    return terms, all_subject_totals


def _overall_average_from_totals(totals):
    if not totals:
        return Decimal("0.00")
    return (sum(totals, Decimal("0.00")) / Decimal(len(totals))).quantize(Decimal("0.01"))


def _latest_published_value(terms):
    return max(
        (term["published_at"] for term in terms if term.get("published_at")),
        default=None,
    )


def _parse_datetime(value):
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _hydrate_snapshot_payload(payload):
    hydrated = dict(payload or {})
    terms = []
    for term in hydrated.get("terms", []):
        row = dict(term)
        row["published_at"] = _parse_datetime(row.get("published_at"))
        terms.append(row)
    hydrated["terms"] = terms
    hydrated["published_at"] = _parse_datetime(hydrated.get("published_at"))
    return hydrated


def _session_transcript_payload_from_compilations(*, student, session):
    compilations = _transcript_compilations_for_student(student, session=session)
    terms, totals = _build_transcript_terms_from_compilations(
        student=student,
        compilations=compilations,
    )
    overall_average = _overall_average_from_totals(totals)
    latest_published = _latest_published_value(terms)
    return {
        "document_type": PDFDocumentType.TRANSCRIPT,
        "student_id": student.id,
        "student_bio": {
            "name": student_display_name(student),
            "student_number": getattr(getattr(student, "student_profile", None), "student_number", student.username),
        },
        "session_name": session.name,
        "terms": terms,
        "term_count": len(terms),
        "overall_average": overall_average,
        "grade_key": _grade_key_payload(),
        "published_at": latest_published,
    }


def upsert_transcript_session_record(*, student, session, generated_by):
    payload = _session_transcript_payload_from_compilations(student=student, session=session)
    digest = payload_sha256(payload)
    record, _ = TranscriptSessionRecord.objects.update_or_create(
        student=student,
        session=session,
        defaults={
            "generated_by": generated_by if getattr(generated_by, "is_authenticated", False) else None,
            "payload_hash": digest,
            "payload": _to_primitive(payload),
            "source_compilation_count": payload["term_count"],
            "published_at": payload.get("published_at"),
            "metadata": {"term_count": payload["term_count"]},
        },
    )
    return record


def snapshot_transcript_session_records(*, session, generated_by):
    student_ids = list(
        ClassResultCompilation.objects.filter(
            status=ClassCompilationStatus.PUBLISHED,
            session=session,
            student_records__student__isnull=False,
        )
        .values_list("student_records__student_id", flat=True)
        .distinct()
    )
    students = User.objects.filter(id__in=student_ids).order_by("id")
    count = 0
    for student in students:
        upsert_transcript_session_record(
            student=student,
            session=session,
            generated_by=generated_by,
        )
        count += 1
    return count


def _build_full_transcript_payload(*, student):
    compilations = _transcript_compilations_for_student(student)
    sessions_map = {}
    for compilation in compilations:
        sessions_map[compilation.session_id] = compilation.session

    snapshot_records = {
        row.session_id: row
        for row in TranscriptSessionRecord.objects.filter(student=student).select_related("session")
    }
    terms = []
    all_subject_totals = []
    for session_id, session in sorted(sessions_map.items(), key=lambda item: item[1].name):
        if session.is_closed and session_id in snapshot_records:
            session_payload = _hydrate_snapshot_payload(snapshot_records[session_id].payload)
        else:
            session_payload = _session_transcript_payload_from_compilations(
                student=student,
                session=session,
            )
        session_terms = session_payload.get("terms", [])
        terms.extend(session_terms)
        for term in session_terms:
            for subject_row in term.get("subject_rows", []):
                try:
                    all_subject_totals.append(Decimal(str(subject_row.get("total", 0))))
                except Exception:
                    continue
    overall_average = _overall_average_from_totals(all_subject_totals)
    latest_published = _latest_published_value(terms)
    return {
        "document_type": PDFDocumentType.TRANSCRIPT,
        "student_id": student.id,
        "student_bio": {
            "name": student_display_name(student),
            "student_number": getattr(getattr(student, "student_profile", None), "student_number", student.username),
        },
        "terms": terms,
        "term_count": len(terms),
        "overall_average": overall_average,
        "grade_key": _grade_key_payload(),
        "published_at": latest_published,
    }


def build_transcript_payload(*, student, session=None):
    if session is not None:
        if session.is_closed:
            snapshot = TranscriptSessionRecord.objects.filter(student=student, session=session).first()
            if snapshot:
                return _hydrate_snapshot_payload(snapshot.payload)
        return _session_transcript_payload_from_compilations(student=student, session=session)

    return _build_full_transcript_payload(student=student)


def available_student_transcript_sessions(student):
    session_ids = set(
        ClassResultCompilation.objects.filter(
            status=ClassCompilationStatus.PUBLISHED,
            student_records__student=student,
        ).values_list("session_id", flat=True)
    )
    snapshot_session_ids = set(
        TranscriptSessionRecord.objects.filter(student=student).values_list("session_id", flat=True)
    )
    merged_ids = sorted(session_ids | snapshot_session_ids)
    if not merged_ids:
        return AcademicSession.objects.none()
    return AcademicSession.objects.filter(id__in=merged_ids).order_by("-name")


def _verification_url(request, artifact):
    return build_portal_url(
        request,
        "landing",
        reverse("pdfs:verify", kwargs={"artifact_id": artifact.id}),
        query={"hash": artifact.payload_hash},
    )


def create_pdf_artifact(
    *,
    document_type,
    payload_hash,
    student,
    generated_by,
    session=None,
    term=None,
    compilation=None,
    published_at=None,
    source_label="",
    metadata=None,
):
    return PDFArtifact.objects.create(
        document_type=document_type,
        student=student,
        generated_by=generated_by if getattr(generated_by, "is_authenticated", False) else None,
        session=session,
        term=term,
        compilation=compilation,
        published_at=published_at,
        payload_hash=payload_hash,
        source_label=source_label,
        metadata=metadata or {},
    )


def render_pdf_bytes(*, template_name, context):
    try:
        from weasyprint import HTML
    except OSError as exc:
        raise RuntimeError(
            "WeasyPrint runtime dependencies are missing on this machine. "
            "Install GTK/Pango libraries for Windows before generating PDFs."
        ) from exc
    html = render_to_string(template_name, context)
    return HTML(string=html, base_url=str(settings.ROOT_DIR)).write_pdf()


def generate_term_report_pdf(*, request, student, compilation, generated_by):
    payload = build_term_report_payload(student=student, compilation=compilation)
    digest = payload_sha256(payload)
    artifact = create_pdf_artifact(
        document_type=PDFDocumentType.TERM_REPORT,
        payload_hash=digest,
        student=student,
        generated_by=generated_by,
        session=compilation.session,
        term=compilation.term,
        compilation=compilation,
        published_at=payload.get("published_at"),
        source_label=f"{compilation.academic_class.display_name or compilation.academic_class.code} {compilation.term.get_name_display()}",
        metadata={"subject_count": payload["subject_count"]},
    )
    verification_url = _verification_url(request, artifact)
    finance_profile = FinanceInstitutionProfile.objects.first()
    show_bank_on_result_pdf = bool(
        finance_profile
        and finance_profile.show_on_result_pdf
        and finance_profile.school_bank_name
        and finance_profile.school_account_name
        and finance_profile.school_account_number
    )
    school_profile_record = school_profile()
    context = {
        "generated_at": timezone.now(),
        "payload": payload,
        "artifact": artifact,
        "school_profile": school_profile_record,
        "logo_data_uri": school_logo_data_uri(),
        "watermark_data_uri": school_logo_data_uri(),
        "student_photo_data_uri": student_profile_photo_data_uri(student),
        "principal_signature_data_uri": principal_signature_data_uri(preferred_user=generated_by),
        "school_stamp_data_uri": school_stamp_data_uri(),
        "verification_url": verification_url,
        "verification_qr_data_uri": qr_code_data_uri(verification_url),
        "finance_profile": finance_profile,
        "show_bank_on_result_pdf": show_bank_on_result_pdf,
    }
    pdf_bytes = render_pdf_bytes(template_name="pdfs/term_report_pdf.html", context=context)
    return pdf_bytes, artifact


def generate_cumulative_report_pdf(*, request, student, compilation, generated_by):
    payload = build_cumulative_report_payload(student=student, compilation=compilation)
    digest = payload_sha256(payload)
    artifact = create_pdf_artifact(
        document_type=PDFDocumentType.CUMULATIVE_REPORT,
        payload_hash=digest,
        student=student,
        generated_by=generated_by,
        session=compilation.session,
        term=compilation.term,
        compilation=compilation,
        published_at=timezone.now(),
        source_label=f"Cumulative promotion report {compilation.session.name}",
        metadata={
            "subject_count": payload["subject_count"],
            "is_complete": payload["is_complete"],
            "missing_terms": payload["missing_terms"],
        },
    )
    verification_url = _verification_url(request, artifact)
    context = {
        "generated_at": timezone.now(),
        "payload": payload,
        "artifact": artifact,
        "school_profile": school_profile(),
        "logo_data_uri": school_logo_data_uri(),
        "watermark_data_uri": school_logo_data_uri(),
        "student_photo_data_uri": student_profile_photo_data_uri(student),
        "principal_signature_data_uri": principal_signature_data_uri(preferred_user=generated_by),
        "school_stamp_data_uri": school_stamp_data_uri(),
        "verification_url": verification_url,
        "verification_qr_data_uri": qr_code_data_uri(verification_url),
    }
    pdf_bytes = render_pdf_bytes(template_name="pdfs/cumulative_report_pdf.html", context=context)
    return pdf_bytes, artifact


def generate_transcript_pdf(*, request, student, generated_by, session=None):
    payload = build_transcript_payload(student=student, session=session)
    digest = payload_sha256(payload)
    source_label = "Multi-session transcript"
    if session is not None:
        source_label = f"Session transcript ({session.name})"
    artifact = create_pdf_artifact(
        document_type=PDFDocumentType.TRANSCRIPT,
        payload_hash=digest,
        student=student,
        generated_by=generated_by,
        session=session,
        published_at=payload.get("published_at"),
        source_label=source_label,
        metadata={
            "term_count": payload["term_count"],
            "session_name": session.name if session is not None else "",
        },
    )
    verification_url = _verification_url(request, artifact)
    school_profile_record = school_profile()
    context = {
        "generated_at": timezone.now(),
        "payload": payload,
        "artifact": artifact,
        "school_profile": school_profile_record,
        "logo_data_uri": school_logo_data_uri(),
        "watermark_data_uri": school_logo_data_uri(),
        "verification_url": verification_url,
        "verification_qr_data_uri": qr_code_data_uri(verification_url),
    }
    pdf_bytes = render_pdf_bytes(template_name="pdfs/transcript_pdf.html", context=context)
    return pdf_bytes, artifact


def generate_performance_analysis_pdf(*, request, student, compilation, generated_by):
    from apps.results.analytics import build_student_performance_report

    payload = build_student_performance_report(
        student=student,
        session=compilation.session,
        term=compilation.term,
    )
    digest = payload_sha256(payload)
    artifact = create_pdf_artifact(
        document_type=PDFDocumentType.PERFORMANCE_ANALYSIS,
        payload_hash=digest,
        student=student,
        generated_by=generated_by,
        session=compilation.session,
        term=compilation.term,
        compilation=compilation,
        published_at=getattr(compilation, "published_at", None),
        source_label=f"Performance analysis {compilation.session.name} {compilation.term.get_name_display()}",
        metadata={"subject_count": len(payload.get("subject_rows", []))},
    )
    verification_url = _verification_url(request, artifact)
    context = {
        "generated_at": timezone.now(),
        "payload": payload,
        "artifact": artifact,
        "school_profile": school_profile(),
        "logo_data_uri": school_logo_data_uri(),
        "student_photo_data_uri": student_profile_photo_data_uri(student),
        "principal_signature_data_uri": principal_signature_data_uri(preferred_user=generated_by),
        "school_stamp_data_uri": school_stamp_data_uri(),
        "verification_url": verification_url,
        "verification_qr_data_uri": qr_code_data_uri(verification_url),
    }
    pdf_bytes = render_pdf_bytes(template_name="pdfs/performance_analysis_pdf.html", context=context)
    return pdf_bytes, artifact


def available_student_compilations(student):
    return (
        ClassResultCompilation.objects.filter(
            status=ClassCompilationStatus.PUBLISHED,
            student_records__student=student,
        )
        .select_related("academic_class", "session", "term")
        .distinct()
        .order_by("-session__name", "-term__name", "academic_class__code")
    )


def can_staff_download_term_report(*, user, compilation):
    role_codes = user.get_all_role_codes()
    if role_codes & {ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL, ROLE_BURSAR}:
        return True
    if ROLE_FORM_TEACHER in role_codes and compilation.form_teacher_id == user.id:
        return True
    if role_codes & {ROLE_DEAN, ROLE_SUBJECT_TEACHER, ROLE_FORM_TEACHER}:
        return TeacherSubjectAssignment.objects.filter(
            teacher=user,
            academic_class=_instructional_class(compilation.academic_class),
            session=compilation.session,
            term=compilation.term,
            is_active=True,
        ).exists()
    return False
