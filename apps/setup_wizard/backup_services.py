from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

from django.conf import settings
from django.core import management
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.setup_wizard.services import get_setup_state


@dataclass
class BackupArchivePayload:
    filename: str
    archive_bytes: bytes
    metadata: dict
    media_file_count: int


def _sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _db_dump_json(path: Path):
    with path.open("w", encoding="utf-8") as stream:
        management.call_command("dumpdata", indent=2, stdout=stream)


def _media_manifest(media_root: Path):
    files = []
    if not media_root.exists():
        return files
    for row in sorted(media_root.rglob("*")):
        if not row.is_file():
            continue
        relative = row.relative_to(media_root).as_posix()
        files.append(
            {
                "path": relative,
                "size": row.stat().st_size,
                "sha256": _sha256_file(row),
            }
        )
    return files


def create_local_backup_archive(*, actor=None):
    now = timezone.now()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    filename = f"ndga_backup_{stamp}.zip"
    media_root = Path(settings.MEDIA_ROOT)
    setup_state = get_setup_state()

    with tempfile.TemporaryDirectory(prefix="ndga-backup-") as temp_dir:
        temp_dir_path = Path(temp_dir)
        db_dump_path = temp_dir_path / "db.json"
        _db_dump_json(db_dump_path)
        media_files = _media_manifest(media_root)
        metadata = {
            "generated_at": now.isoformat(),
            "generated_by": (
                actor.username
                if getattr(actor, "is_authenticated", False)
                else "system"
            ),
            "ndga_base_domain": settings.NDGA_BASE_DOMAIN,
            "setup_state": setup_state.state,
            "current_session": (
                setup_state.current_session.name
                if setup_state.current_session_id
                else ""
            ),
            "current_term": (
                setup_state.current_term.name
                if setup_state.current_term_id
                else ""
            ),
            "django_settings_module": settings.SETTINGS_MODULE,
            "media_file_count": len(media_files),
            "format_version": 1,
        }
        manifest = {
            "generated_at": now.isoformat(),
            "file_count": len(media_files),
            "files": media_files,
        }

        archive_stream = io.BytesIO()
        with zipfile.ZipFile(archive_stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("metadata.json", json.dumps(metadata, indent=2, sort_keys=True))
            archive.writestr("media/manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
            archive.write(db_dump_path, arcname="database/db.json")
            for row in media_files:
                src_path = media_root / row["path"]
                archive.write(src_path, arcname=f"media/files/{row['path']}")

    return BackupArchivePayload(
        filename=filename,
        archive_bytes=archive_stream.getvalue(),
        metadata=metadata,
        media_file_count=len(media_files),
    )


def inspect_backup_archive(archive_path):
    archive_path = Path(archive_path)
    if not archive_path.exists():
        raise ValidationError("Backup archive not found.")
    if archive_path.suffix.lower() != ".zip":
        raise ValidationError("Backup file must be a .zip archive.")

    with zipfile.ZipFile(archive_path, "r") as archive:
        members = set(archive.namelist())
        required = {"metadata.json", "database/db.json", "media/manifest.json"}
        missing_required = sorted(required - members)
        if missing_required:
            raise ValidationError(
                "Backup archive is missing required entries: "
                + ", ".join(missing_required)
            )

        metadata = json.loads(archive.read("metadata.json").decode("utf-8"))
        if not isinstance(metadata, dict):
            raise ValidationError("Invalid backup metadata format.")

        manifest = json.loads(archive.read("media/manifest.json").decode("utf-8"))
        if not isinstance(manifest, dict):
            raise ValidationError("Invalid media manifest format.")
        media_files = manifest.get("files", [])
        if not isinstance(media_files, list):
            raise ValidationError("Invalid media manifest format.")

        database_dump_bytes = len(archive.read("database/db.json"))

    return {
        "archive": str(archive_path),
        "archive_size_bytes": archive_path.stat().st_size,
        "archive_sha256": _sha256_file(archive_path),
        "required_entries_present": True,
        "member_count": len(members),
        "database_dump_bytes": database_dump_bytes,
        "generated_at": metadata.get("generated_at", ""),
        "generated_by": metadata.get("generated_by", ""),
        "setup_state": metadata.get("setup_state", ""),
        "current_session": metadata.get("current_session", ""),
        "current_term": metadata.get("current_term", ""),
        "media_file_count": len(media_files),
        "manifest_media_files": int(manifest.get("file_count") or len(media_files)),
        "format_version": metadata.get("format_version", 1),
    }


def _clear_media_root(media_root: Path):
    if not media_root.exists():
        return
    for row in sorted(media_root.rglob("*"), reverse=True):
        if row.is_file():
            row.unlink(missing_ok=True)
        elif row.is_dir():
            try:
                row.rmdir()
            except OSError:
                continue


def _safe_media_target(*, media_root: Path, relative_path: str):
    target = (media_root / relative_path).resolve()
    media_root_resolved = media_root.resolve()
    if media_root_resolved == target or media_root_resolved in target.parents:
        return target
    raise ValidationError("Unsafe media path in backup archive.")


def restore_local_backup_archive(
    *,
    archive_path,
    flush_database=True,
    clear_media=True,
):
    archive_path = Path(archive_path)
    if not archive_path.exists():
        raise ValidationError("Backup archive not found.")
    if archive_path.suffix.lower() != ".zip":
        raise ValidationError("Backup file must be a .zip archive.")

    media_root = Path(settings.MEDIA_ROOT)
    media_root.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "r") as archive:
        members = set(archive.namelist())
        required = {"metadata.json", "database/db.json", "media/manifest.json"}
        missing_required = sorted(required - members)
        if missing_required:
            raise ValidationError(
                "Backup archive is missing required entries: "
                + ", ".join(missing_required)
            )

        manifest = json.loads(archive.read("media/manifest.json").decode("utf-8"))
        media_files = manifest.get("files", []) if isinstance(manifest, dict) else []
        if not isinstance(media_files, list):
            raise ValidationError("Invalid media manifest format.")

        with tempfile.TemporaryDirectory(prefix="ndga-restore-") as temp_dir:
            db_dump_path = Path(temp_dir) / "db.json"
            db_dump_path.write_bytes(archive.read("database/db.json"))

            if flush_database:
                management.call_command("flush", "--noinput")
            management.call_command("loaddata", str(db_dump_path))

        if clear_media:
            _clear_media_root(media_root)

        restored_count = 0
        for row in media_files:
            relative = (row.get("path") or "").strip().replace("\\", "/")
            if not relative:
                continue
            source_name = f"media/files/{relative}"
            if source_name not in members:
                continue
            target_path = _safe_media_target(media_root=media_root, relative_path=relative)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(source_name, "r") as source, target_path.open("wb") as target:
                shutil.copyfileobj(source, target)
            restored_count += 1

    checksum_mismatch_count = 0
    for row in media_files:
        relative = (row.get("path") or "").strip().replace("\\", "/")
        expected = (row.get("sha256") or "").strip().lower()
        if not relative or not expected:
            continue
        target_path = _safe_media_target(media_root=media_root, relative_path=relative)
        if not target_path.exists():
            checksum_mismatch_count += 1
            continue
        if _sha256_file(target_path).lower() != expected:
            checksum_mismatch_count += 1

    return {
        "archive": str(archive_path),
        "restored_media_files": restored_count,
        "manifest_media_files": len(media_files),
        "checksum_mismatches": checksum_mismatch_count,
        "database_flushed": bool(flush_database),
        "media_cleared": bool(clear_media),
    }
