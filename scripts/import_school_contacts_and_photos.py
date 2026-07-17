import io
import os
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "core.settings.local"))

import django

django.setup()

import pdfplumber
from PIL import Image
from django.core.files.base import ContentFile
from django.db import transaction

from apps.accounts.models import StudentProfile
from apps.academics.models import AcademicSession, StudentClassEnrollment
from apps.notifications.services import normalize_whatsapp_phone


SOURCE_DIR = Path(os.getenv("NDGA_IMPORT_SOURCE_DIR", str(ROOT / "SCHOOL FOLDER")))
CONTACTS_PDF = SOURCE_DIR / "Parents emails and contacts.pdf"
PHOTO_CLASS_FOLDERS = ("JS1", "JS2", "JS3", "SS1")
EMAIL_RE = re.compile(r"[\w.\-+']+@[\w.\-]+\.\w+")


def collapse(value):
    return " ".join(str(value or "").split())


def normalize_class_token(value):
    cleaned = collapse(value).upper().replace("JSS", "JS").replace("SSS", "SS")
    return re.sub(r"[^A-Z0-9]+", "", cleaned)


def normalize_name_token(value):
    cleaned = collapse(value).upper()
    cleaned = cleaned.replace("’", "'").replace("'", "")
    cleaned = cleaned.replace("-", " ")
    return re.sub(r"[^A-Z0-9]+", "", cleaned)

def name_key_variants(value):
    cleaned = collapse(value).upper()
    cleaned = cleaned.replace("’", "'").replace("‘", "'").replace("â€™", "'").replace("'", "")
    cleaned = cleaned.replace("-", " ")
    parts = [part for part in re.split(r"[^A-Z0-9]+", cleaned) if part]
    if not parts:
        return {""}
    variants = {"".join(parts)}
    if len(parts) >= 2:
        variants.add("".join(reversed(parts)))
        variants.add("".join(sorted(parts)))
    if len(parts) == 3:
        variants.add("".join([parts[1], parts[0], parts[2]]))
        variants.add("".join([parts[1], parts[2], parts[0]]))
    return variants


def student_display_name(profile):
    user = profile.user
    parts = [user.last_name, user.first_name, profile.middle_name]
    return collapse(" ".join(part for part in parts if part))


def parse_email_values(raw_value):
    matches = EMAIL_RE.findall(str(raw_value or ""))
    cleaned = []
    seen = set()
    for match in matches:
        value = match.strip().strip(".,;:").lower()
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    return cleaned


def parse_phone_values(raw_value):
    cleaned = []
    seen = set()
    parts = re.split(r"[;\n,/]+", str(raw_value or ""))
    for part in parts:
        value = normalize_whatsapp_phone(part)
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    return cleaned


def parse_contact_rows(pdf_path):
    rows = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if not table:
                    continue
                header = [collapse(cell).upper() for cell in table[0]]
                if len(header) < 4 or header[:4] != ["CLASS", "STUDENT NAME", "EMAILS", "WHATSAPP NUMBERS"]:
                    continue
                for raw_row in table[1:]:
                    cells = list(raw_row or [])
                    while len(cells) < 4:
                        cells.append("")
                    class_label, student_name, emails, phones = [collapse(cell) for cell in cells[:4]]
                    if not class_label or not student_name:
                        continue
                    rows.append(
                        {
                            "class_code": normalize_class_token(class_label),
                            "student_name": student_name,
                            "name_key": normalize_name_token(student_name),
                            "emails": parse_email_values(emails),
                            "phones": parse_phone_values(phones),
                        }
                    )
    return rows


def build_student_lookup(session_name):
    session = AcademicSession.objects.filter(name=session_name).first()
    if session is None:
        raise ValueError(f"Session '{session_name}' was not found.")
    lookup = {}
    class_buckets = defaultdict(list)
    duplicates = defaultdict(list)
    enrollments = (
        StudentClassEnrollment.objects.filter(session=session, is_active=True)
        .select_related("student", "student__student_profile", "academic_class", "academic_class__base_class")
        .order_by("student_id")
    )
    for enrollment in enrollments:
        profile = getattr(enrollment.student, "student_profile", None)
        if profile is None:
            continue
        instructional = enrollment.academic_class.instructional_class
        variants = name_key_variants(student_display_name(profile))
        duplicate_hit = False
        for variant in variants:
            key = (normalize_class_token(instructional.code), variant)
            if key in lookup:
                duplicates[key].append(profile.student_number)
                duplicate_hit = True
                continue
            lookup[key] = profile
        if duplicate_hit:
            continue
        class_buckets[normalize_class_token(instructional.code)].append(profile)
    return session, lookup, class_buckets, duplicates


def find_fuzzy_profile(*, class_code, name_key, class_buckets, used_profile_ids):
    candidates = []
    for profile in class_buckets.get(class_code, []):
        if profile.id in used_profile_ids:
            continue
        candidate_variants = name_key_variants(student_display_name(profile))
        ratio = max(SequenceMatcher(None, name_key, candidate_name).ratio() for candidate_name in candidate_variants)
        if ratio >= 0.86:
            candidates.append((ratio, profile))
    candidates.sort(key=lambda row: row[0], reverse=True)
    if not candidates:
        return None
    best_ratio, best_profile = candidates[0]
    second_ratio = candidates[1][0] if len(candidates) > 1 else 0
    if best_ratio >= 0.92 or (best_ratio - second_ratio) >= 0.05:
        return best_profile
    return None


def _square_crop(image):
    width, height = image.size
    size = min(width, height)
    left = (width - size) // 2
    top = (height - size) // 2
    image = image.crop((left, top, left + size, top + size)).convert("RGB")
    if size > 720:
        image = image.resize((720, 720), Image.Resampling.LANCZOS)
    return image


def build_photo_lookup(session_name):
    session = AcademicSession.objects.filter(name=session_name).first()
    if session is None:
        raise ValueError(f"Session '{session_name}' was not found.")
    lookup = {}
    enrollments = (
        StudentClassEnrollment.objects.filter(session=session, is_active=True)
        .select_related("student", "student__student_profile", "academic_class", "academic_class__base_class")
        .order_by("student_id")
    )
    for enrollment in enrollments:
        profile = getattr(enrollment.student, "student_profile", None)
        if profile is None:
            continue
        instructional = enrollment.academic_class.instructional_class
        match = re.search(r"(\d+)$", profile.student_number or "")
        if not match:
            continue
        lookup[(normalize_class_token(instructional.code), match.group(1))] = profile
    return lookup


@transaction.atomic
def import_guardian_contacts(*, session_name):
    session, student_lookup, class_buckets, duplicates = build_student_lookup(session_name)
    contact_rows = parse_contact_rows(CONTACTS_PDF)
    used_profile_ids = set()
    summary = {
        "session": session.name,
        "rows": len(contact_rows),
        "matched": 0,
        "fuzzy_matched": 0,
        "updated_profiles": 0,
        "updated_users": 0,
        "missing": [],
        "duplicates": duplicates,
    }
    for row in contact_rows:
        profile = student_lookup.get((row["class_code"], row["name_key"]))
        if profile is None:
            profile = find_fuzzy_profile(
                class_code=row["class_code"],
                name_key=row["name_key"],
                class_buckets=class_buckets,
                used_profile_ids=used_profile_ids,
            )
            if profile is not None:
                summary["fuzzy_matched"] += 1
        if profile is None:
            summary["missing"].append(f"{row['class_code']} | {row['student_name']}")
            continue
        used_profile_ids.add(profile.id)
        user = profile.user
        profile_changed = False
        user_changed = False
        emails = row["emails"]
        phones = row["phones"]
        if emails:
            primary_email = emails[0]
            secondary_email = emails[1] if len(emails) > 1 else ""
            if profile.guardian_email != primary_email:
                profile.guardian_email = primary_email
                profile_changed = True
            target_user_email = secondary_email or primary_email
            if target_user_email and user.email != target_user_email:
                user.email = target_user_email
                user_changed = True
        if phones:
            joined_phones = " / ".join(phones)
            if profile.guardian_phone != joined_phones:
                profile.guardian_phone = joined_phones
                profile_changed = True
        if profile_changed:
            profile.save(update_fields=["guardian_email", "guardian_phone", "updated_at"])
            summary["updated_profiles"] += 1
        if user_changed:
            user.save(update_fields=["email"])
            summary["updated_users"] += 1
        summary["matched"] += 1
    return summary


@transaction.atomic
def import_student_photos(*, session_name):
    photo_lookup = build_photo_lookup(session_name)
    summary = {
        "matched": 0,
        "updated": 0,
        "missing": [],
    }
    for folder_name in PHOTO_CLASS_FOLDERS:
        folder = SOURCE_DIR / folder_name
        if not folder.exists():
            continue
        class_code = normalize_class_token(folder_name)
        for image_path in sorted(folder.glob("*.jpg")):
            profile = photo_lookup.get((class_code, image_path.stem))
            if profile is None:
                summary["missing"].append(f"{folder_name}/{image_path.name}")
                continue
            with Image.open(image_path) as image:
                cropped = _square_crop(image)
                buffer = io.BytesIO()
                cropped.save(buffer, format="JPEG", quality=92, optimize=True)
            filename = f"{profile.student_number.replace('/', '-').lower()}.jpg"
            profile.profile_photo.save(filename, ContentFile(buffer.getvalue()), save=False)
            profile.save(update_fields=["profile_photo", "updated_at"])
            summary["matched"] += 1
            summary["updated"] += 1
    return summary


def print_summary(label, summary):
    print(f"[{label}]")
    for key, value in summary.items():
        if key in {"missing", "duplicates"}:
            continue
        print(f"{key}: {value}")
    missing = summary.get("missing") or []
    if missing:
        print(f"missing_count: {len(missing)}")
        for item in missing[:20]:
            print(f"missing: {item}")
    duplicates = summary.get("duplicates") or {}
    if duplicates:
        duplicate_items = list(duplicates.items())
        print(f"duplicate_keys: {len(duplicate_items)}")
        for key, values in duplicate_items[:10]:
            print(f"duplicate: {key} => {values}")


if __name__ == "__main__":
    session_name = os.getenv("NDGA_IMPORT_SESSION", "2025/2026")
    contact_summary = import_guardian_contacts(session_name=session_name)
    photo_summary = import_student_photos(session_name=session_name)
    print_summary("CONTACTS", contact_summary)
    print_summary("PHOTOS", photo_summary)
