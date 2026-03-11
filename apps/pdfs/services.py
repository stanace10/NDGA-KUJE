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
from apps.tenancy.utils import build_portal_url


TERM_ORDER = {"FIRST": 1, "SECOND": 2, "THIRD": 3}
DEFAULT_BEHAVIOR_LABELS = {
    "discipline": "Discipline",
    "punctuality": "Punctuality",
    "respect": "Respect & Courtesy",
    "leadership": "Leadership",
    "sports": "Sports & Teamwork",
    "neatness": "Neatness",
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
        return ""
    path = getattr(profile.school_stamp, "path", "")
    if not path or not Path(path).exists():
        return ""
    return _read_file_as_data_uri(path)


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
        return ""

    path = getattr(signature.signature_image, "path", "")
    if not path or not Path(path).exists():
        return ""
    return _read_file_as_data_uri(path)


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
    value = float(total or 0)
    if value >= 75:
        return "Excellent"
    if value >= 60:
        return "Very Good"
    if value >= 50:
        return "Good"
    if value >= 40:
        return "Fair"
    return "Needs Improvement"


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
    exam_values = [Decimal(row.get("exam") or 0) * (Decimal("100") / Decimal("60")) for row in subject_rows]
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
                "rating": _score_remark(score, ""),
            }
        )
    return payload


def _class_position_summary(*, compilation, target_student_id):
    student_ids = _compilation_student_ids(compilation)
    if not student_ids:
        return {"position": None, "class_average": Decimal("0.00"), "class_size": 0}
    score_rows = list(
        StudentSubjectScore.objects.filter(
            result_sheet__academic_class=_instructional_class(compilation.academic_class),
            result_sheet__session=compilation.session,
            result_sheet__term=compilation.term,
            student_id__in=student_ids,
        )
        .values("student_id")
        .annotate(total=Sum("grand_total"), subject_count=Count("id"))
    )
    ranking_rows = []
    for row in score_rows:
        subject_count = int(row.get("subject_count") or 0)
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


def _subject_rows_for_compilation(*, student, compilation):
    instructional_class = _instructional_class(compilation.academic_class)
    sheets = list(
        ResultSheet.objects.filter(
            academic_class=instructional_class,
            session=compilation.session,
            term=compilation.term,
            status=ResultSheetStatus.PUBLISHED,
        )
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
        if not score:
            continue
        peer_scores = grouped_scores.get(sheet.id, [])
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
        exam_component_total = Decimal(score.objective or 0) + Decimal(score.theory or 0)
        average_total = (sum(totals, Decimal("0.00")) / Decimal(len(totals))).quantize(Decimal("0.01")) if totals else Decimal("0.00")
        row_total = _format_decimal(score.grand_total)
        rows.append(
            {
                "subject": sheet.subject.name,
                "ca1": _format_decimal(score.ca1),
                "ca2": _format_decimal(score.ca2),
                "ca3": _format_decimal(score.ca3),
                "assignment": _format_decimal(score.ca4),
                "ca4": _format_decimal(score.ca4),
                "objective": _format_decimal(score.objective),
                "theory": _format_decimal(score.theory),
                "exam": _format_decimal(exam_component_total),
                "total": row_total,
                "grade": score.grade,
                "remark": _score_remark(row_total, score.grade),
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


def build_term_report_payload(*, student, compilation):
    if compilation.status != ClassCompilationStatus.PUBLISHED:
        raise ValueError("Term report can be generated only for published class compilations.")

    subject_rows = _subject_rows_for_compilation(student=student, compilation=compilation)
    subject_count = len(subject_rows)
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
    fail_count = len([row for row in subject_rows if (row.get("grade") or "F") == "F"])
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

    school_days = int(attendance_snapshot.get("valid_school_days", 0) or 0) if attendance_snapshot else 0
    present_days = int(attendance_snapshot.get("present_days", 0) or 0) if attendance_snapshot else 0
    absent_days = int(attendance_snapshot.get("absent_days", 0) or 0) if attendance_snapshot else 0
    behavior_rows = _behavior_metric_rows(record) if record else []
    class_code = compilation.academic_class.display_name or compilation.academic_class.code
    level_code = compilation.academic_class.instructional_class.display_name or compilation.academic_class.instructional_class.code
    layout_padding_rows = list(range(max(0, 20 - subject_count)))

    return {
        "document_type": PDFDocumentType.TERM_REPORT,
        "student_id": student.id,
        "student_bio": _build_student_bio(student=student, compilation=compilation),
        "session_name": compilation.session.name,
        "term_name": compilation.term.get_name_display(),
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
        "dean_comment": comment_bundle["dean_comment"],
        "principal_comment": comment_bundle["principal_comment"],
        "comment_headline": comment_bundle["headline"],
        "subject_rows": subject_rows,
        "subject_count": subject_count,
        "total_mark_obtainable": subject_count * 100,
        "cumulative_total": cumulative_total.quantize(Decimal("0.01")),
        "average": average,
        "class_average": position_summary["class_average"],
        "class_position": _ordinal(position_summary["position"]) if position_summary["position"] else "-",
        "class_size": position_summary["class_size"],
        "grade_key": [
            {
                "grade": row.grade,
                "min_score": row.min_score,
                "max_score": row.max_score,
            }
            for row in get_grade_key_rows()
        ],
        "layout_padding_rows": layout_padding_rows,
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
            "office_held": getattr(record, "office_held", "") if record else "",
            "notable_contribution": getattr(record, "notable_contribution", "") if record else "",
        },
        "approval_trail": _approval_trail(compilation=compilation),
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
        "grade_key": [
            {
                "grade": row.grade,
                "min_score": row.min_score,
                "max_score": row.max_score,
            }
            for row in get_grade_key_rows()
        ],
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
        "grade_key": [
            {
                "grade": row.grade,
                "min_score": row.min_score,
                "max_score": row.max_score,
            }
            for row in get_grade_key_rows()
        ],
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
