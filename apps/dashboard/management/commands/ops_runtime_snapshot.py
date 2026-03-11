import json

from django.core.management.base import BaseCommand

from core.ops import collect_ops_runtime_snapshot


class Command(BaseCommand):
    help = "Print a runtime snapshot for database, cache, disk, sync backlog, and audit health."

    def handle(self, *args, **options):
        snapshot = collect_ops_runtime_snapshot()
        self.stdout.write(json.dumps(snapshot, indent=2, sort_keys=True))
