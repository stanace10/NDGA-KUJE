"""Apply the requested Dean and SS3 Mathematics staff credentials/assignment."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "core.settings"))

import django

django.setup()

from django.db import transaction

from apps.accounts.models import User
from apps.academics.models import AcademicSession, TeacherSubjectAssignment, Term
from apps.audit.models import AuditCategory, AuditStatus
from apps.audit.services import log_event


@transaction.atomic
def run():
    dean = User.objects.get(pk=229, primary_role__code="DEAN")
    emmanuel = User.objects.get(pk=7, staff_profile__staff_id="NDGAK/STAFF/002")

    collisions = User.objects.filter(
        username__in=["ndgak/dean", "ndgak/staff/002"],
    ).exclude(pk__in=[dean.pk, emmanuel.pk])
    if collisions.exists():
        raise RuntimeError(f"Requested username already belongs to another account: {list(collisions.values_list('id', 'username'))}")

    before = {
        "dean_username": dean.username,
        "emmanuel_username": emmanuel.username,
    }

    dean.username = "ndgak/dean"
    dean.set_password("admin")
    dean.must_change_password = False
    dean.save(update_fields=["username", "password", "must_change_password"])

    emmanuel.username = "ndgak/staff/002"
    emmanuel.set_password("ndgak/002")
    emmanuel.must_change_password = False
    emmanuel.save(update_fields=["username", "password", "must_change_password"])

    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="THIRD")
    ftm_assignment = TeacherSubjectAssignment.objects.select_for_update().get(
        academic_class__code="SS3",
        subject__code="FTM",
        session=session,
        term=term,
        is_active=True,
    )
    previous_teacher = ftm_assignment.teacher
    ftm_assignment.teacher = emmanuel
    ftm_assignment.full_clean()
    ftm_assignment.save(update_fields=["teacher", "updated_at"])

    log_event(
        category=AuditCategory.AUTH,
        event_type="EXAM_ACCOUNT_CREDENTIALS_UPDATED",
        status=AuditStatus.SUCCESS,
        actor=dean,
        metadata={
            **before,
            "dean_new_username": dean.username,
            "emmanuel_new_username": emmanuel.username,
            "emmanuel_staff_id": emmanuel.staff_profile.staff_id,
            "ss3_ftm_previous_teacher": previous_teacher.username,
            "ss3_ftm_new_teacher": emmanuel.username,
            "passwords_redacted": True,
        },
    )

    print(
        {
            "dean": {
                "id": dean.id,
                "username": dean.username,
                "password_verified": dean.check_password("admin"),
            },
            "emmanuel": {
                "id": emmanuel.id,
                "staff_id": emmanuel.staff_profile.staff_id,
                "username": emmanuel.username,
                "password_verified": emmanuel.check_password("ndgak/002"),
            },
            "ss3_assignments": list(
                TeacherSubjectAssignment.objects.filter(
                    academic_class__code="SS3",
                    subject__code__in=["MTH", "FTM"],
                    session=session,
                    term=term,
                    is_active=True,
                )
                .order_by("subject__code")
                .values_list("subject__code", "teacher__username")
            ),
        }
    )


if __name__ == "__main__":
    run()
