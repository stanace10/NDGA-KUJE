from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import zipfile

import boto3
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


@dataclass
class PostgresDumpBackupPayload:
    filename: str
    file_path: str
    size_bytes: int
    sha256: str
    generated_at: str
    s3_bucket: str = ""
    s3_key: str = ""


def _sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_pg_backup_output_dir(output_dir=None):
    base_dir = Path(getattr(settings, "ROOT_DIR", Path.cwd()))
    target = Path(output_dir or getattr(settings, "BACKUP_PG_OUTPUT_DIR", "backups/postgres"))
    if not target.is_absolute():
        target = base_dir / target
    target.mkdir(parents=True, exist_ok=True)
    return target


def _prune_old_files(*, directory: Path, pattern: str, keep_count: int):
    keep_count = max(int(keep_count or 1), 1)
    candidates = sorted(directory.glob(pattern), key=lambda row: row.stat().st_mtime, reverse=True)
    for stale in candidates[keep_count:]:
        stale.unlink(missing_ok=True)


def _db_dump_json(path: Path):
    with path.open("w", encoding="utf-8") as stream:
        management.call_command("dumpdata", indent=2, stdout=stream)


def create_postgres_dump_backup(
    *,
    output_dir=None,
    s3_bucket="",
    s3_prefix="",
    upload_to_s3=False,
    keep_local_count=None,
):
    db_settings = settings.DATABASES["default"]
    db_engine = (db_settings.get("ENGINE") or "").lower()
    if "postgresql" not in db_engine:
        raise ValidationError("PostgreSQL pg_dump backup requires a PostgreSQL database engine.")

    target_dir = _resolve_pg_backup_output_dir(output_dir=output_dir)
    now = timezone.now()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    filename = f"ndga_pg_{stamp}.dump"
    file_path = target_dir / filename

    command = [
        "pg_dump",
        "-Fc",
        "--no-owner",
        "--no-privileges",
        "-h",
        str(db_settings.get("HOST") or "127.0.0.1"),
        "-p",
        str(db_settings.get("PORT") or "5432"),
        "-U",
        str(db_settings.get("USER") or ""),
        "-d",
        str(db_settings.get("NAME") or ""),
        "-f",
        str(file_path),
    ]
    env = os.environ.copy()
    env["PGPASSWORD"] = str(db_settings.get("PASSWORD") or "")
    try:
        subprocess.run(
            command,
            check=True,
            env=env,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ValidationError("pg_dump is not installed in this runtime.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise ValidationError(f"pg_dump failed: {stderr or exc}") from exc

    digest = _sha256_file(file_path)
    payload = PostgresDumpBackupPayload(
        filename=filename,
        file_path=str(file_path),
        size_bytes=file_path.stat().st_size,
        sha256=digest,
        generated_at=now.isoformat(),
    )

    if upload_to_s3:
        bucket = (s3_bucket or getattr(settings, "BACKUP_PG_S3_BUCKET", "")).strip()
        if not bucket:
            raise ValidationError("S3 upload requested but BACKUP_PG_S3_BUCKET is not configured.")
        prefix = (s3_prefix or getattr(settings, "BACKUP_PG_S3_PREFIX", "nightly")).strip().strip("/")
        key = f"{prefix}/{filename}" if prefix else filename
        session = boto3.session.Session(
            region_name=(
                getattr(settings, "AWS_S3_REGION_NAME", "")
                or os.environ.get("AWS_REGION", "")
                or None
            )
        )
        session.client("s3").upload_file(str(file_path), bucket, key)
        payload.s3_bucket = bucket
        payload.s3_key = key

    metadata_path = file_path.with_suffix(".json")
    metadata_path.write_text(
        json.dumps(
            {
                "filename": payload.filename,
                "generated_at": payload.generated_at,
                "size_bytes": payload.size_bytes,
                "sha256": payload.sha256,
                "s3_bucket": payload.s3_bucket,
                "s3_key": payload.s3_key,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    _prune_old_files(
        directory=target_dir,
        pattern="ndga_pg_*.dump",
        keep_count=keep_local_count or getattr(settings, "BACKUP_PG_KEEP_LOCAL_COUNT", 14),
    )
    _prune_old_files(
        directory=target_dir,
        pattern="ndga_pg_*.json",
        keep_count=keep_local_count or getattr(settings, "BACKUP_PG_KEEP_LOCAL_COUNT", 14),
    )
    return payload


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
