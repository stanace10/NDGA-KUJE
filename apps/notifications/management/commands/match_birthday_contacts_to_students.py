from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.notifications.management.commands.import_birthday_contacts import _match_student_guardian
from apps.notifications.models import BirthdayContact, BirthdayContactType


class Command(BaseCommand):
    help = "Match imported parent birthday contacts to student guardian email and phone records."

    def handle(self, *args, **options):
        matched = 0
        total = 0
        for contact in BirthdayContact.objects.filter(contact_type=BirthdayContactType.PARENT, is_active=True):
            total += 1
            if _match_student_guardian(contact):
                matched += 1
        self.stdout.write(self.style.SUCCESS(f"Parent birthday matching complete: matched={matched} checked={total}"))
