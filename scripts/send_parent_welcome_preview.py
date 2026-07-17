from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "core.settings.local"))

import django

django.setup()

from django.contrib.auth import get_user_model

from apps.dashboard.models import SchoolProfile
from apps.notifications.services import send_email_event


PREVIEW_RECIPIENT = os.getenv("NDGA_PREVIEW_RECIPIENT", "szubby10@gmail.com")
PREVIEW_PASSWORD = os.getenv("NDGA_PREVIEW_PASSWORD", "Preview#2026")
LOGIN_URL = "https://student.ndgakuje.org/auth/login/?audience=student"


def main():
    User = get_user_model()
    student = (
        User.objects.select_related("student_profile")
        .filter(student_profile__student_number="NDGAK/PREVIEW/SS3")
        .first()
    )
    if not student:
        student = (
            User.objects.select_related("student_profile")
            .filter(username__startswith="preview-20260327-", student_profile__isnull=False)
            .order_by("username")
            .first()
        )
    if not student:
        raise RuntimeError("No preview student was found for the welcome email preview.")

    profile = getattr(student, "student_profile", None)
    school = SchoolProfile.load()
    ward_name = " ".join(
        part for part in [student.last_name, student.first_name, getattr(profile, "middle_name", "")] if str(part).strip()
    ).strip() or student.get_full_name() or student.username
    class_name = ""
    active_enrollment = student.class_enrollments.select_related("academic_class").filter(is_active=True).first()
    if active_enrollment:
        class_name = active_enrollment.academic_class.display_name or active_enrollment.academic_class.code

    body_text = (
        f"Dear Parent/Guardian,\n\n"
        f"Welcome to the official communication channel of {school.school_name or 'Notre Dame Girls Academy'}.\n\n"
        f"We are pleased to share this parent communication preview with you. Your ward's school login details are below so that you can monitor academic activities directly from the student portal.\n\n"
        f"Ward Name: {ward_name}\n"
        f"Class: {class_name or '-'}\n"
        f"Admission Number: {getattr(profile, 'student_number', student.username)}\n"
        f"Login ID: {student.username}\n"
        f"Temporary Password: {PREVIEW_PASSWORD}\n"
        f"Student Portal: {LOGIN_URL}\n\n"
        f"Students are currently away for the Easter break. We wish you and your family a peaceful, joyful, and blessed Easter holiday.\n\n"
        f"This official school email channel will be used for result updates, school notices, fee/payment notices, attendance alerts, and other important communication concerning your child.\n\n"
        f"Warm regards,\n"
        f"{school.school_name or 'Notre Dame Girls Academy'}\n"
        f"{school.contact_email or 'office@ndgakuje.org'}"
    )

    body_html = f"""
    <p style="margin:0 0 16px; font-size:15px; line-height:1.8; color:#475569;">
      Welcome to the official communication channel of <strong>{school.school_name or 'Notre Dame Girls Academy'}</strong>.
    </p>
    <p style="margin:0 0 16px; font-size:15px; line-height:1.8; color:#475569;">
      We are pleased to share this parent communication preview with you. Your ward's login details are included below so that parents can always access the student portal directly when needed.
    </p>
    <div style="margin:0 0 20px; border:1px solid #dbe4f0; border-radius:18px; overflow:hidden;">
      <div style="background:#173a66; color:#ffffff; padding:12px 16px; font-size:13px; font-weight:700; letter-spacing:0.06em; text-transform:uppercase;">
        Ward Access Details
      </div>
      <div style="padding:16px; background:#f8fbff;">
        <p style="margin:0 0 10px; font-size:14px; line-height:1.7; color:#0f172a;"><strong>Ward Name:</strong> {ward_name}</p>
        <p style="margin:0 0 10px; font-size:14px; line-height:1.7; color:#0f172a;"><strong>Class:</strong> {class_name or '-'}</p>
        <p style="margin:0 0 10px; font-size:14px; line-height:1.7; color:#0f172a;"><strong>Admission Number:</strong> {getattr(profile, 'student_number', student.username)}</p>
        <p style="margin:0 0 10px; font-size:14px; line-height:1.7; color:#0f172a;"><strong>Login ID:</strong> {student.username}</p>
        <p style="margin:0 0 0; font-size:14px; line-height:1.7; color:#0f172a;"><strong>Temporary Password:</strong> {PREVIEW_PASSWORD}</p>
      </div>
    </div>
    <div style="margin:0 0 20px; padding:18px 20px; border-radius:18px; background:#fff8e8; border:1px solid #f2d08a;">
      <p style="margin:0 0 8px; font-size:14px; font-weight:700; color:#8b5a00;">Easter Break Wishes</p>
      <p style="margin:0; font-size:14px; line-height:1.8; color:#5b4630;">
        Students are currently away for the Easter break. We wish you and your family a peaceful, joyful, and blessed Easter holiday.
      </p>
    </div>
    <p style="margin:0 0 18px; font-size:15px; line-height:1.8; color:#475569;">
      This official school email channel will be used for result updates, school announcements, fee/payment notices, attendance alerts, and other important communication concerning your child.
    </p>
    <div style="margin:0 0 8px;">
      <a href="{LOGIN_URL}" style="display:inline-block; background:#0f2747; color:#ffffff; text-decoration:none; padding:12px 18px; border-radius:14px; font-size:14px; font-weight:700;">
        Open Student Portal
      </a>
    </div>
    """

    result = send_email_event(
        to_emails=[PREVIEW_RECIPIENT],
        subject="Welcome to Notre Dame Girls Academy Official Communication",
        body_text=body_text,
        body_html=body_html,
        metadata={
            "event": "PARENT_WELCOME_PREVIEW",
            "preview_student": getattr(profile, "student_number", student.username),
            "preview_only": True,
        },
    )
    print(
        {
            "recipient": PREVIEW_RECIPIENT,
            "student_number": getattr(profile, "student_number", student.username),
            "username": student.username,
            "provider": getattr(result, "provider", ""),
            "detail": getattr(result, "detail", ""),
            "success": getattr(result, "success", False),
        }
    )


if __name__ == "__main__":
    main()
