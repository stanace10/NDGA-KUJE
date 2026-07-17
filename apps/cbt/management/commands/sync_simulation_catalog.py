from __future__ import annotations

import json
from urllib.request import urlopen

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.cbt.services import seed_curated_simulation_library, seed_simulation_library_rows


class Command(BaseCommand):
    help = "Seed NDGA CBT simulation library from curated catalog or remote JSON manifest."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            required=True,
            help="User account to attribute seeded wrappers to (usually IT manager).",
        )
        parser.add_argument(
            "--manifest-url",
            help="Optional JSON URL. Expected format: list[dict] or {'rows': list[dict]}.",
        )

    def _fetch_manifest_rows(self, manifest_url):
        try:
            with urlopen(manifest_url, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise CommandError(f"Could not fetch simulation manifest: {exc}") from exc

        rows = payload.get("rows") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise CommandError("Manifest format invalid. Expected list or {'rows': [...]} structure.")
        return rows

    def handle(self, *args, **options):
        username = options["username"].strip()
        manifest_url = (options.get("manifest_url") or "").strip()

        actor = User.objects.filter(username=username).first()
        if actor is None:
            raise CommandError(f"User '{username}' not found.")

        if manifest_url:
            rows = self._fetch_manifest_rows(manifest_url)
            result = seed_simulation_library_rows(actor=actor, rows=rows)
            source_label = f"remote manifest ({manifest_url})"
        else:
            result = seed_curated_simulation_library(actor=actor)
            source_label = "built-in curated catalog"

        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"Simulation catalog sync complete from {source_label}: "
                    f"created={result['created']}, updated={result['updated']}, "
                    f"unchanged={result['skipped']}, total={result['total_seed_rows']}"
                )
            )
        )
