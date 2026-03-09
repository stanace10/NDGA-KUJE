from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from apps.accounts.models import User
from apps.cbt.models import (
    CBTSimulationCallbackType,
    CBTSimulationScoreMode,
    CBTSimulationSourceProvider,
    CBTSimulationToolCategory,
    CBTSimulationWrapperStatus,
    SimulationWrapper,
)


def _safe_extract_zip(zip_path: Path, destination: Path):
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            member_name = member.filename or ""
            member_path = Path(member_name)
            if not member_name.strip():
                continue
            if member_path.is_absolute() or ".." in member_path.parts:
                raise CommandError(f"Unsafe ZIP member path: {member_name}")
            archive.extract(member, destination)


def _resolve_entry_file(root: Path, preferred_entry: str):
    if preferred_entry:
        preferred_path = root / preferred_entry
        if preferred_path.exists() and preferred_path.is_file():
            return preferred_path

    index_candidates = sorted(root.rglob("index.html"))
    if index_candidates:
        return index_candidates[0]
    html_candidates = sorted(root.rglob("*.html"))
    if html_candidates:
        return html_candidates[0]
    raise CommandError(f"No HTML entry file found under {root}")


class Command(BaseCommand):
    help = (
        "Import simulation library rows from JSON manifest and materialize offline bundles "
        "(from local paths and/or download URLs) into MEDIA_ROOT/sims."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="",
            help="IT actor username/email (alias: --actor).",
        )
        parser.add_argument(
            "--actor",
            default="",
            help="IT actor username/email (alias for --username).",
        )
        parser.add_argument(
            "--manifest-file",
            type=str,
            help="Path to local JSON manifest (list or {'rows': [...]}).",
        )
        parser.add_argument(
            "--manifest-url",
            type=str,
            help="Remote JSON manifest URL (list or {'rows': [...]}).",
        )
        parser.add_argument(
            "--source-root",
            type=str,
            default="",
            help="Base folder for relative local_path entries in the manifest.",
        )
        parser.add_argument(
            "--approve",
            action="store_true",
            help="Mark imported wrappers as approved.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview import actions without writing files/database rows.",
        )

    def _load_manifest_rows(self, *, manifest_file: str, manifest_url: str):
        if bool(manifest_file) == bool(manifest_url):
            raise CommandError("Provide exactly one of --manifest-file or --manifest-url.")

        if manifest_file:
            manifest_path = Path(manifest_file).resolve()
            if not manifest_path.exists():
                raise CommandError(f"Manifest file not found: {manifest_path}")
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            try:
                with urlopen(manifest_url, timeout=30) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                raise CommandError(f"Could not fetch manifest URL: {exc}") from exc

        rows = payload.get("rows") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise CommandError("Manifest must be list or {'rows': [...]} format.")
        return rows

    def _materialize_offline_asset(
        self,
        *,
        row: dict,
        source_root: Path,
        target_root: Path,
        media_prefix: str,
        dry_run: bool,
    ):
        local_path = (row.get("local_path") or "").strip()
        download_url = (row.get("download_url") or "").strip()
        entry_file = (row.get("entry_file") or "").strip()
        slug = slugify(row.get("tool_name") or "simulation")
        target_dir = target_root / slug

        if not local_path and not download_url:
            return ""

        if dry_run:
            return f"{media_prefix}/sims/{slug}/{entry_file or 'index.html'}"

        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        if download_url:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                with urlopen(download_url, timeout=60) as response:
                    temp_file.write(response.read())
            try:
                _safe_extract_zip(temp_path, target_dir)
            finally:
                temp_path.unlink(missing_ok=True)
        else:
            source_path = Path(local_path)
            if not source_path.is_absolute():
                source_path = source_root / source_path
            source_path = source_path.resolve()
            if not source_path.exists():
                raise CommandError(f"local_path does not exist: {source_path}")
            if source_path.is_file():
                if source_path.suffix.lower() != ".zip":
                    raise CommandError(
                        f"local_path file must be a .zip bundle or directory: {source_path}"
                    )
                _safe_extract_zip(source_path, target_dir)
            else:
                shutil.copytree(source_path, target_dir, dirs_exist_ok=True)

        launch_file = _resolve_entry_file(target_dir, entry_file)
        relative = launch_file.relative_to(Path(settings.MEDIA_ROOT)).as_posix()
        return f"{media_prefix}/{relative}"

    def handle(self, *args, **options):
        actor_key = (options.get("username") or "").strip() or (options.get("actor") or "").strip()
        if not actor_key:
            raise CommandError("Provide --username or --actor.")
        actor = User.objects.filter(username=actor_key).first() or User.objects.filter(
            email=actor_key
        ).first()
        if actor is None:
            raise CommandError(f"Actor '{actor_key}' not found.")

        rows = self._load_manifest_rows(
            manifest_file=(options.get("manifest_file") or "").strip(),
            manifest_url=(options.get("manifest_url") or "").strip(),
        )

        dry_run = bool(options.get("dry_run"))
        approve = bool(options.get("approve"))
        status = CBTSimulationWrapperStatus.APPROVED if approve else CBTSimulationWrapperStatus.DRAFT

        source_root = Path(options.get("source_root") or ".").resolve()
        media_root = Path(settings.MEDIA_ROOT).resolve()
        target_root = media_root / "sims"
        media_prefix = settings.MEDIA_URL.rstrip("/")
        if not dry_run:
            target_root.mkdir(parents=True, exist_ok=True)

        valid_categories = {code for code, _ in CBTSimulationToolCategory.choices}
        valid_providers = {code for code, _ in CBTSimulationSourceProvider.choices}
        valid_scores = {code for code, _ in CBTSimulationScoreMode.choices}
        valid_callbacks = {code for code, _ in CBTSimulationCallbackType.choices}

        created = 0
        updated = 0
        skipped = 0

        for row in rows:
            if not isinstance(row, dict):
                skipped += 1
                continue
            tool_name = (row.get("tool_name") or "").strip()
            category = (row.get("tool_category") or "").strip().upper()
            if not tool_name or category not in valid_categories:
                skipped += 1
                continue

            provider = (row.get("source_provider") or CBTSimulationSourceProvider.OTHER).strip().upper()
            if provider not in valid_providers:
                provider = CBTSimulationSourceProvider.OTHER

            score_mode = (row.get("score_mode") or CBTSimulationScoreMode.VERIFY).strip().upper()
            if score_mode not in valid_scores:
                score_mode = CBTSimulationScoreMode.VERIFY

            callback_type = (row.get("scoring_callback_type") or CBTSimulationCallbackType.POST_MESSAGE).strip().upper()
            if callback_type not in valid_callbacks:
                callback_type = CBTSimulationCallbackType.POST_MESSAGE

            offline_url = self._materialize_offline_asset(
                row=row,
                source_root=source_root,
                target_root=target_root,
                media_prefix=media_prefix,
                dry_run=dry_run,
            )
            online_url = (row.get("online_url") or "").strip()
            if not offline_url and not online_url:
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"[dry-run] {tool_name} | category={category} | offline={bool(offline_url)} | online={bool(online_url)}"
                )
                continue

            defaults = {
                "tool_type": (row.get("tool_type") or "HTML5 Simulation").strip(),
                "source_provider": provider,
                "source_reference_url": (row.get("source_reference_url") or "").strip(),
                "description": (row.get("description") or "").strip(),
                "online_url": online_url,
                "offline_asset_path": offline_url,
                "score_mode": score_mode,
                "max_score": str(row.get("max_score") or "10.00"),
                "scoring_callback_type": callback_type,
                "evidence_required": bool(row.get("evidence_required", score_mode != CBTSimulationScoreMode.AUTO)),
                "status": status,
                "is_active": True,
                "created_by": actor,
            }
            wrapper, was_created = SimulationWrapper.objects.get_or_create(
                tool_name=tool_name,
                tool_category=category,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                changed = []
                for field_name, field_value in defaults.items():
                    if field_name == "created_by" and wrapper.created_by_id:
                        continue
                    if getattr(wrapper, field_name) != field_value:
                        setattr(wrapper, field_name, field_value)
                        changed.append(field_name)
                if changed:
                    wrapper.save(update_fields=[*changed, "updated_at"])
                    updated += 1
                else:
                    skipped += 1
                    continue
            self.stdout.write(self.style.SUCCESS(f"[ok] {tool_name}"))

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry-run completed. rows={len(rows)}, would_process={len(rows) - skipped}"
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Simulation manifest import completed: created={created}, updated={updated}, skipped={skipped}, total={len(rows)}"
            )
        )
