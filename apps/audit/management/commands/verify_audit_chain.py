from django.core.management.base import BaseCommand, CommandError

from apps.audit.services import verify_audit_chain


class Command(BaseCommand):
    help = "Verify the tamper-evident audit hash chain."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Optional maximum number of oldest events to verify.",
        )

    def handle(self, *args, **options):
        summary = verify_audit_chain(limit=options["limit"] or None)
        if not summary["ok"]:
            for row in summary["mismatches"]:
                self.stderr.write(
                    self.style.ERROR(
                        f"Audit chain mismatch on event {row['event_id']}: {row['issue']}"
                    )
                )
            raise CommandError("Audit chain verification failed.")
        self.stdout.write(
            self.style.SUCCESS(
                f"Audit chain verified successfully for {summary['verified_count']} event(s)."
            )
        )