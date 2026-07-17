from __future__ import annotations

import os
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.cbt.models import (
    CBTSimulationCallbackType,
    CBTSimulationScoreMode,
    CBTSimulationSourceProvider,
    CBTSimulationToolCategory,
    CBTSimulationWrapperStatus,
    SimulationWrapper,
)


DEFAULT_SLUGS = [
    "circuit-construction-kit-dc",
    "projectile-motion",
    "balancing-chemical-equations",
    "acid-base-solutions",
    "graphing-lines",
]

SLUG_LABELS = {
    "circuit-construction-kit-dc": ("PhET Circuit Construction Kit", CBTSimulationToolCategory.SCIENCE),
    "projectile-motion": ("PhET Projectile Motion Lab", CBTSimulationToolCategory.SCIENCE),
    "balancing-chemical-equations": ("PhET Balancing Chemical Equations", CBTSimulationToolCategory.SCIENCE),
    "acid-base-solutions": ("PhET Acid-Base Solutions", CBTSimulationToolCategory.SCIENCE),
    "graphing-lines": ("PhET Graphing Lines", CBTSimulationToolCategory.MATHEMATICS),
}


def _guess_category_for_slug(slug):
    math_tokens = {"graph", "line", "algebra", "fraction", "area", "equation", "ratio", "slope"}
    if any(token in slug for token in math_tokens):
        return CBTSimulationToolCategory.MATHEMATICS
    return CBTSimulationToolCategory.SCIENCE


def _detect_phet_html_root():
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = []
    if local_app_data.exists():
        temp_root = local_app_data / "Temp"
        if temp_root.exists():
            candidates.extend(temp_root.glob("ns*.tmp/7z-out/resources/app/resources/simulations/html"))
        candidates.extend(local_app_data.glob("Programs/**/resources/app/resources/simulations/html"))

    existing = [path for path in candidates if path.exists()]
    if not existing:
        raise CommandError(
            "Could not auto-detect local PhET HTML simulation folder. "
            "Pass --source <path> explicitly."
        )
    existing.sort(key=lambda row: len(str(row)))
    return existing[0]


class Command(BaseCommand):
    help = "Import HTML5 PhET simulations from local PhET desktop app into NDGA media/sims library."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=str,
            help="Path to local PhET html simulation root (contains slug folders).",
        )
        parser.add_argument(
            "--slugs",
            type=str,
            default="",
            help="Comma separated PhET simulation slugs to import.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Import every slug folder found under source path.",
        )
        parser.add_argument(
            "--actor",
            type=str,
            help="Actor username/email for created_by.",
        )
        parser.add_argument(
            "--approve",
            action="store_true",
            help="Mark imported wrappers as approved.",
        )

    def handle(self, *args, **options):
        source_arg = options.get("source")
        source_root = Path(source_arg).resolve() if source_arg else _detect_phet_html_root()
        if not source_root.exists():
            raise CommandError(f"Source path does not exist: {source_root}")

        actor = None
        actor_key = (options.get("actor") or "").strip()
        if actor_key:
            actor = User.objects.filter(email=actor_key).first() or User.objects.filter(username=actor_key).first()
            if actor is None:
                raise CommandError(f"Actor not found: {actor_key}")

        approve = bool(options.get("approve"))
        status = CBTSimulationWrapperStatus.APPROVED if approve else CBTSimulationWrapperStatus.DRAFT
        raw_slugs = [row.strip() for row in (options.get("slugs") or "").split(",") if row.strip()]
        if options.get("all"):
            slugs = sorted([row.name for row in source_root.iterdir() if row.is_dir()])
        elif raw_slugs:
            slugs = raw_slugs
        else:
            slugs = list(DEFAULT_SLUGS)
        if not slugs:
            raise CommandError("No slugs provided.")

        created = 0
        updated = 0
        skipped = 0
        media_root = Path(settings.MEDIA_ROOT)
        media_root.mkdir(parents=True, exist_ok=True)
        media_prefix = settings.MEDIA_URL.rstrip("/")

        for slug in slugs:
            sim_dir = source_root / slug
            if not sim_dir.exists():
                self.stdout.write(self.style.WARNING(f"[skip] missing slug folder: {slug}"))
                skipped += 1
                continue

            html_candidates = sorted(sim_dir.glob("*_all.html"))
            if not html_candidates:
                html_candidates = sorted(sim_dir.glob("*.html"))
            if not html_candidates:
                self.stdout.write(self.style.WARNING(f"[skip] no html launch file: {slug}"))
                skipped += 1
                continue
            launch_file = html_candidates[0]

            target_dir = media_root / "sims" / f"phet-{slug}"
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(sim_dir, target_dir)

            label, category = SLUG_LABELS.get(
                slug,
                (f"PhET {slug.replace('-', ' ').title()}", _guess_category_for_slug(slug)),
            )
            launch_url = f"{media_prefix}/sims/phet-{slug}/{launch_file.name}"

            wrapper, was_created = SimulationWrapper.objects.get_or_create(
                tool_name=label,
                tool_category=category,
                defaults={
                    "tool_type": "HTML5 Simulation",
                    "source_provider": CBTSimulationSourceProvider.PHET,
                    "source_reference_url": f"https://phet.colorado.edu/sims/html/{slug}/latest/",
                    "description": "Imported from local PhET desktop package for offline NDGA usage.",
                    "online_url": "",
                    "offline_asset_path": launch_url,
                    "score_mode": CBTSimulationScoreMode.VERIFY,
                    "max_score": "10.00",
                    "scoring_callback_type": CBTSimulationCallbackType.POST_MESSAGE,
                    "evidence_required": True,
                    "status": status,
                    "created_by": actor,
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
            else:
                wrapper.tool_type = "HTML5 Simulation"
                wrapper.source_provider = CBTSimulationSourceProvider.PHET
                wrapper.source_reference_url = f"https://phet.colorado.edu/sims/html/{slug}/latest/"
                wrapper.description = "Imported from local PhET desktop package for offline NDGA usage."
                wrapper.online_url = ""
                wrapper.offline_asset_path = launch_url
                wrapper.score_mode = CBTSimulationScoreMode.VERIFY
                wrapper.max_score = "10.00"
                wrapper.scoring_callback_type = CBTSimulationCallbackType.POST_MESSAGE
                wrapper.evidence_required = True
                wrapper.status = status
                wrapper.is_active = True
                if actor and not wrapper.created_by_id:
                    wrapper.created_by = actor
                wrapper.full_clean()
                wrapper.save()
                updated += 1

            self.stdout.write(self.style.SUCCESS(f"[ok] {label} -> {launch_url}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete. Created={created}, Updated={updated}, Skipped={skipped}. Source={source_root}"
            )
        )
