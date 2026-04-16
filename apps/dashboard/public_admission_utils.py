from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from django.core.files.storage import default_storage
from django.utils.dateparse import parse_date, parse_datetime

from apps.dashboard.models import (
    PublicAdmissionPaymentMode,
    PublicAdmissionPaymentStatus,
    PublicSiteSubmission,
)


HOW_FOUND_US_LABELS = {
    "PARISH": "Parish",
    "FRIENDS": "Friends",
    "ADVERTISEMENT": "Advertisement",
    "REPUTATION": "Reputation",
    "PRESENT_SCHOOL": "Present School",
    "OTHER": "Other",
}

BOARDING_LABELS = {
    "BOARDING": "Boarding",
    "DAY": "Day Student",
}


def _clean(value):
    return str(value or "").strip()


def _display_date(value):
    raw = _clean(value)
    if not raw:
        return ""
    parsed = parse_datetime(raw)
    if parsed is not None:
        return parsed.strftime("%d %b %Y")
    parsed_date = parse_date(raw)
    if parsed_date is not None:
        return parsed_date.strftime("%d %b %Y")
    return raw


def _stored_file_name(path):
    raw = _clean(path)
    if not raw:
        return ""
    return Path(raw).name


def _stored_file_url(path):
    raw = _clean(path)
    if not raw:
        return ""


def _field_file_url(field_file):
    try:
        return field_file.url if field_file else ""
    except Exception:
        return ""


def _field_file_name(field_file):
    try:
        return field_file.name if field_file else ""
    except Exception:
        return ""
    try:
        return default_storage.url(raw)
    except Exception:
        return ""


def build_public_admission_snapshot(submission: PublicSiteSubmission):
    payload = deepcopy(submission.admission_form_payload())
    student = dict(payload.get("student_details") or {})
    religion = dict(payload.get("religious_background") or {})
    placement = dict(payload.get("school_placement") or {})
    parents = dict(payload.get("parents") or {})
    statement = dict(payload.get("discovery_and_statement") or {})
    declaration = dict(payload.get("declaration") or {})
    documents = dict(payload.get("documents") or {})
    education_history = list(placement.get("education_history") or [])

    how_found_value = _clean(statement.get("how_found_us")).upper()
    how_found_label = HOW_FOUND_US_LABELS.get(how_found_value, _clean(statement.get("how_found_us")))
    if how_found_value == "OTHER" and _clean(statement.get("how_found_us_other")):
        how_found_label = f"Other - {_clean(statement.get('how_found_us_other'))}"

    record = {
        "student": {
            "surname": _clean(student.get("surname")),
            "first_name": _clean(student.get("first_name")),
            "middle_name": _clean(student.get("middle_name")),
            "full_name": _clean(submission.applicant_name),
            "address": _clean(student.get("address")) or _clean(submission.residential_address),
            "date_of_birth": _display_date(student.get("date_of_birth")) or (
                submission.applicant_date_of_birth.strftime("%d %b %Y") if submission.applicant_date_of_birth else ""
            ),
            "nationality": _clean(student.get("nationality")),
            "state_of_origin": _clean(student.get("state_of_origin")),
            "local_government_area": _clean(student.get("local_government_area")),
            "home_town": _clean(student.get("home_town")),
            "has_disability_or_learning_difficulty": bool(student.get("has_disability_or_learning_difficulty")),
            "medical_notes": _clean(student.get("medical_notes")) or _clean(submission.medical_notes),
            "passport_photo_url": _field_file_url(getattr(submission, "passport_photo", None)),
        },
        "religious_background": {
            "religion": _clean(religion.get("religion")),
            "parish_name": _clean(religion.get("parish_name")),
        },
        "school_placement": {
            "boarding_option": BOARDING_LABELS.get(
                _clean(placement.get("boarding_option")).upper(),
                _clean(placement.get("boarding_option")) or _clean(submission.boarding_option),
            ),
            "intended_class": _clean(placement.get("intended_class")) or _clean(submission.intended_class),
            "sibling_details": _clean(placement.get("sibling_details")),
            "present_school": _clean(placement.get("present_school")) or _clean(submission.previous_school),
            "head_teacher_name": _clean(placement.get("head_teacher_name")),
            "head_teacher_signature_stamp": _clean(placement.get("head_teacher_signature_stamp")),
            "head_teacher_date": _display_date(placement.get("head_teacher_date")),
            "education_history": education_history,
        },
        "parents": {
            "primary_guardian_name": _clean(parents.get("primary_guardian_name")) or _clean(submission.guardian_name),
            "primary_guardian_email": _clean(parents.get("primary_guardian_email")) or _clean(submission.guardian_email),
            "primary_guardian_phone": _clean(parents.get("primary_guardian_phone")) or _clean(submission.guardian_phone),
            "father_full_name": _clean(parents.get("father_full_name")),
            "father_contact_address": _clean(parents.get("father_contact_address")),
            "father_occupation": _clean(parents.get("father_occupation")),
            "father_place_of_work": _clean(parents.get("father_place_of_work")),
            "father_phone": _clean(parents.get("father_phone")),
            "father_email": _clean(parents.get("father_email")),
            "mother_full_name": _clean(parents.get("mother_full_name")),
            "mother_contact_address": _clean(parents.get("mother_contact_address")),
            "mother_occupation": _clean(parents.get("mother_occupation")),
            "mother_place_of_work": _clean(parents.get("mother_place_of_work")),
            "mother_phone": _clean(parents.get("mother_phone")),
            "mother_email": _clean(parents.get("mother_email")),
            "emergency_contact_name": _clean(parents.get("emergency_contact_name")),
            "emergency_contact_address": _clean(parents.get("emergency_contact_address")),
            "emergency_contact_phone": _clean(parents.get("emergency_contact_phone")),
        },
        "statement": {
            "how_found_us": how_found_label,
            "personal_statement": _clean(statement.get("personal_statement")),
        },
        "declaration": {
            "parent_guardian_name": _clean(declaration.get("parent_guardian_name")),
            "parent_guardian_signature": _clean(declaration.get("parent_guardian_signature")),
            "parent_guardian_date": _display_date(declaration.get("parent_guardian_date")),
            "student_name": _clean(declaration.get("student_name")),
            "student_signature": _clean(declaration.get("student_signature")),
            "student_date": _display_date(declaration.get("student_date")),
        },
        "documents": [
            {
                "label": "Passport Photograph",
                "name": _stored_file_name(_field_file_name(getattr(submission, "passport_photo", None))),
                "url": _field_file_url(getattr(submission, "passport_photo", None)),
            },
            {
                "label": "Second Passport Photograph",
                "name": _stored_file_name(documents.get("supporting_passport_photo_path")),
                "url": _stored_file_url(documents.get("supporting_passport_photo_path")),
            },
            {
                "label": "Birth Certificate",
                "name": _stored_file_name(_field_file_name(getattr(submission, "birth_certificate", None))) or _clean(
                    documents.get("birth_certificate_name")
                ),
                "url": _field_file_url(getattr(submission, "birth_certificate", None)),
            },
            {
                "label": "Last School Result",
                "name": _stored_file_name(_field_file_name(getattr(submission, "school_result", None))) or _clean(
                    documents.get("school_result_name")
                ),
                "url": _field_file_url(getattr(submission, "school_result", None)),
            },
            {
                "label": "Medical Fitness Report",
                "name": _stored_file_name(documents.get("medical_fitness_report_path")),
                "url": _stored_file_url(documents.get("medical_fitness_report_path")),
            },
        ],
        "payment": {
            "status": submission.get_payment_status_display(),
            "mode": submission.admission_payment_mode(),
            "mode_badge": submission.payment_mode_badge(),
            "public_pdf_available": submission.public_admission_pdf_available(),
            "staff_pdf_available": submission.payment_status == PublicAdmissionPaymentStatus.PAID,
            "is_paid_online": (
                submission.payment_status == PublicAdmissionPaymentStatus.PAID
                and submission.admission_payment_mode() == PublicAdmissionPaymentMode.ONLINE
            ),
        },
    }
    return record
