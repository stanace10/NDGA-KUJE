from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.finance.prospectus import ensure_prospectus_charges
from apps.finance.services import current_academic_window


class Command(BaseCommand):
    help = "Post or refresh official prospectus fee charges for the active session and term."

    def handle(self, *args, **options):
        session, term = current_academic_window()
        if session is None:
            raise CommandError("No current academic session is configured.")
        result = ensure_prospectus_charges(session=session, term=term)
        self.stdout.write(
            self.style.SUCCESS(
                "Prospectus fees ready: "
                f"classes={result['classes']} created={result['created']} updated={result['updated']}"
            )
        )
