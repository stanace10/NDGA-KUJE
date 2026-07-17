from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.db.models import Q

from apps.academics.models import StudentClassEnrollment
from apps.accounts.models import StudentProfile
from apps.setup_wizard.services import get_setup_state


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
TARGET_STAGES = ("JS1", "JS2", "SS1", "SS2")


def _load_heif_support():
    try:
        from pillow_heif import register_heif_opener
    except Exception:
        return False
    register_heif_opener()
    return True


def _candidate_number(path: Path):
    match = re.match(r"^\s*(\d{2,4})", path.stem)
    return match.group(1) if match else ""


def _target_students(session):
    enrollments = (
        StudentClassEnrollment.objects.select_related("student", "student__student_profile", "academic_class")
        .filter(session=session, is_active=True)
        .filter(
            Q(academic_class__code__istartswith="JS1")
            | Q(academic_class__code__istartswith="JS2")
            | Q(academic_class__code__istartswith="SS1")
            | Q(academic_class__code__istartswith="SS2")
        )
    )
    by_last_number = {}
    for enrollment in enrollments:
        profile = getattr(enrollment.student, "student_profile", None)
        if not profile:
            continue
        number = (profile.student_number or "").strip().split("/")[-1]
        if not number:
            continue
        by_last_number[number] = profile
    return by_last_number


def run(source_dir="/tmp/ndga_profile_import", overwrite=True):
    from PIL import Image, ImageOps

    heif_enabled = _load_heif_support()
    source_root = Path(source_dir)
    if not source_root.exists():
        raise RuntimeError(f"Profile source folder not found: {source_root}")

    setup_state = get_setup_state()
    if not setup_state.current_session_id:
        raise RuntimeError("Current session is not configured.")

    media_root = Path(settings.MEDIA_ROOT)
    target_dir = media_root / "profiles" / "students"
    target_dir.mkdir(parents=True, exist_ok=True)

    profiles = _target_students(setup_state.current_session)
    imported = []
    skipped = []

    for path in sorted(source_root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        number = _candidate_number(path)
        profile = profiles.get(number)
        if not profile:
            skipped.append((path.name, "no active JS1/JS2/SS1/SS2 student matched"))
            continue
        if path.suffix.lower() in {".heic", ".heif"} and not heif_enabled:
            skipped.append((path.name, "HEIC support unavailable"))
            continue
        if profile.profile_photo and not overwrite:
            skipped.append((path.name, "student already has photo"))
            continue

        output_name = f"{profile.student_number.replace('/', '-')}.jpg"
        output_path = target_dir / output_name
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            elif image.mode == "L":
                image = image.convert("RGB")
            # Keep a square, face-friendly crop for circular portal/result display.
            image = ImageOps.fit(image, (900, 900), method=Image.Resampling.LANCZOS, centering=(0.5, 0.38))
            image.save(output_path, format="JPEG", quality=88, optimize=True)

        profile.profile_photo.name = f"profiles/students/{output_name}"
        profile.save(update_fields=["profile_photo", "updated_at"])
        imported.append((profile.student_number, path.name, profile.profile_photo.name))

    return {
        "source_dir": str(source_root),
        "imported_count": len(imported),
        "skipped_count": len(skipped),
        "imported": imported,
        "skipped": skipped[:30],
        "heif_enabled": heif_enabled,
        "target_dir": str(target_dir),
    }


if __name__ == "__main__":
    print(run())
