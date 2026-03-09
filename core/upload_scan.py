from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError


DANGEROUS_EXTENSIONS = {
    ".exe",
    ".dll",
    ".bat",
    ".cmd",
    ".ps1",
    ".sh",
    ".js",
    ".jar",
    ".com",
    ".scr",
    ".msi",
    ".vbs",
    ".hta",
}


def _file_ext(uploaded_file):
    return Path((getattr(uploaded_file, "name", "") or "").lower()).suffix


def _max_bytes_from_mb(size_mb):
    return int(size_mb * 1024 * 1024)


def _read_probe(uploaded_file, max_bytes=4096):
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    chunk = uploaded_file.read(max_bytes) or b""
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    return chunk


def scan_uploaded_file(
    uploaded_file,
    *,
    allowed_extensions,
    max_size_mb,
    allowed_content_prefixes=(),
    text_payload=False,
):
    if uploaded_file is None:
        return uploaded_file

    extension = _file_ext(uploaded_file)
    if extension in DANGEROUS_EXTENSIONS:
        raise ValidationError("Blocked file type for security reasons.")
    if allowed_extensions and extension not in set(allowed_extensions):
        raise ValidationError("Unsupported file type.")

    max_size_bytes = _max_bytes_from_mb(max_size_mb)
    if getattr(uploaded_file, "size", 0) > max_size_bytes:
        raise ValidationError(f"File is too large. Max allowed is {max_size_mb}MB.")

    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    if allowed_content_prefixes and content_type:
        allowed = any(content_type.startswith(prefix) for prefix in allowed_content_prefixes)
        if not allowed:
            raise ValidationError("Unexpected content type for uploaded file.")

    probe = _read_probe(uploaded_file)
    if probe.startswith(b"MZ"):
        raise ValidationError("Executable file signatures are blocked.")
    if text_payload and b"\x00" in probe:
        raise ValidationError("Invalid text payload detected.")

    return uploaded_file


def validate_image_upload(uploaded_file):
    return scan_uploaded_file(
        uploaded_file,
        allowed_extensions={".jpg", ".jpeg", ".png", ".webp"},
        max_size_mb=settings.UPLOAD_SECURITY.get("MAX_IMAGE_MB", 8),
        allowed_content_prefixes=("image/",),
    )


def validate_document_upload(uploaded_file):
    return scan_uploaded_file(
        uploaded_file,
        allowed_extensions={".pdf", ".doc", ".docx", ".txt"},
        max_size_mb=settings.UPLOAD_SECURITY.get("MAX_DOCUMENT_MB", 12),
        allowed_content_prefixes=(
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument",
            "text/plain",
        ),
    )


def validate_json_upload(uploaded_file):
    return scan_uploaded_file(
        uploaded_file,
        allowed_extensions={".json"},
        max_size_mb=settings.UPLOAD_SECURITY.get("MAX_JSON_MB", 15),
        allowed_content_prefixes=("application/json", "text/plain"),
        text_payload=True,
    )


def validate_receipt_upload(uploaded_file):
    return scan_uploaded_file(
        uploaded_file,
        allowed_extensions={".pdf", ".jpg", ".jpeg", ".png", ".webp"},
        max_size_mb=settings.UPLOAD_SECURITY.get("MAX_RECEIPT_MB", 10),
        allowed_content_prefixes=("application/pdf", "image/"),
    )


def validate_simulation_evidence_upload(uploaded_file):
    return scan_uploaded_file(
        uploaded_file,
        allowed_extensions={".pdf", ".jpg", ".jpeg", ".png", ".webp", ".doc", ".docx", ".txt"},
        max_size_mb=settings.UPLOAD_SECURITY.get("MAX_EVIDENCE_MB", 20),
        allowed_content_prefixes=(
            "application/pdf",
            "image/",
            "application/msword",
            "application/vnd.openxmlformats-officedocument",
            "text/plain",
        ),
    )


def validate_simulation_bundle_upload(uploaded_file):
    return scan_uploaded_file(
        uploaded_file,
        allowed_extensions={".zip"},
        max_size_mb=settings.UPLOAD_SECURITY.get("MAX_SIM_BUNDLE_MB", 180),
        allowed_content_prefixes=(
            "application/zip",
            "application/x-zip-compressed",
            "application/octet-stream",
        ),
    )
