"""Non-destructive SQLite backup and isolated restore verification for SEER.

This module deliberately has no scheduler, runtime, or cutover behaviour.  It
uses SQLite's online backup API rather than copying a live database file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


class BackupSafetyError(RuntimeError):
    """Raised before an operation that is not demonstrably non-destructive."""


class BackupVerificationError(RuntimeError):
    """Raised when an isolated restore cannot be verified."""


_DESTRUCTIVE_OPTIONS = {"--apply", "--cutover", "--force", "--overwrite", "--replace", "--delete-source"}
_PRODUCTION_MARKERS = ("production", "prod", "live", "canonical", "primary")


def create_backup(*, source: str | Path, backup_destination: str | Path,
                  manifest_destination: str | Path, source_watermark: str) -> dict[str, Any]:
    """Create a SQLite-consistent snapshot and immutable companion manifest.

    ``source_watermark`` is an opaque, caller-supplied replay boundary.  The
    source checksum is deliberately labelled as a post-snapshot raw-file
    observation: it is useful evidence but is *not* claimed to prove that a
    live SQLite source was point-in-time consistent.
    """
    source_text = str(source)
    source_path = _existing_file(source, "source")
    backup_path = Path(backup_destination)
    manifest_path = Path(manifest_destination)
    _require_nonempty_watermark(source_watermark)
    _require_new_file(backup_path, "backup destination")
    _require_new_file(manifest_path, "manifest destination")
    if backup_path.parent.resolve() != manifest_path.parent.resolve():
        raise BackupSafetyError("manifest destination must be beside the backup destination")
    if backup_path.resolve(strict=False) == source_path.resolve():
        raise BackupSafetyError("backup destination must not be the source database")

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with closing(sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)) as source_db:
            with closing(sqlite3.connect(backup_path)) as destination_db:
                source_db.backup(destination_db)
                destination_db.commit()
    except sqlite3.Error as exc:
        raise BackupSafetyError(f"SQLite-consistent backup failed: {exc}") from exc

    try:
        details = _database_details(backup_path)
        manifest = {
            "format": "seer-sqlite-backup-manifest/v1",
            "created_at_utc": _utc_now(),
            "source_path_as_supplied": source_text,
            "source_watermark": source_watermark,
            "backup_path": str(backup_path),
            "backup_sha256": _sha256(backup_path),
            "source_sha256": _sha256(source_path),
            "source_sha256_scope": (
                "post_snapshot_raw_source_file_observation; not a point-in-time "
                "consistency proof for a live SQLite source"
            ),
            **details,
        }
        _write_immutable_json(manifest_path, manifest)
    except Exception:
        # The backup itself is retained for inspection, but we never claim it
        # completed successfully without its required manifest.
        raise
    return manifest


def verify_backup(*, backup: str | Path, backup_manifest: str | Path,
                  verification_destination: str | Path,
                  verification_manifest_destination: str | Path,
                  source_path: str | Path | None = None) -> dict[str, Any]:
    """Copy a backup into a new isolated target and prove basic recoverability.

    The verification destination is never opened read-write after copy; the
    copied database is opened with SQLite ``mode=ro`` for integrity and count
    checks.  A result manifest is written for both success and expected
    verification failures when its destination is safe and new.
    """
    backup_path = _existing_file(backup, "backup")
    manifest_path = _existing_file(backup_manifest, "backup manifest")
    verification_path = Path(verification_destination)
    result_path = Path(verification_manifest_destination)
    _require_new_file(verification_path, "verification destination")
    _require_new_file(result_path, "verification manifest destination")
    if verification_path.parent.resolve() != result_path.parent.resolve():
        raise BackupSafetyError("verification manifest must be beside the verification destination")
    _refuse_restore_target(verification_path, backup_path, source_path)

    expected = _read_manifest(manifest_path)
    result: dict[str, Any] = {
        "format": "seer-sqlite-restore-verification/v1",
        "verified_at_utc": _utc_now(),
        "backup_path": str(backup_path),
        "backup_manifest_path": str(manifest_path),
        "verification_destination": str(verification_path),
        "status": "failed",
    }
    try:
        actual_checksum = _sha256(backup_path)
        result["backup_sha256"] = actual_checksum
        result["manifest_backup_sha256"] = expected.get("backup_sha256")
        if actual_checksum != expected.get("backup_sha256"):
            raise BackupVerificationError("backup checksum does not match its manifest")
        verification_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(backup_path, verification_path)
        restored = _database_details(verification_path)
        expected_details = {key: expected.get(key) for key in ("schema_migration_version", "table_row_counts")}
        observed_details = {key: restored.get(key) for key in expected_details}
        result["expected_database_details"] = expected_details
        result["observed_database_details"] = observed_details
        if observed_details != expected_details:
            raise BackupVerificationError("restored schema version or table row counts differ from backup manifest")
        result["integrity_check"] = restored["integrity_check"]
        result["status"] = "passed"
    except (OSError, sqlite3.Error, BackupVerificationError) as exc:
        result["error"] = str(exc)
        _write_immutable_json(result_path, result)
        if isinstance(exc, BackupVerificationError):
            raise
        raise BackupVerificationError(f"restore verification failed: {exc}") from exc
    _write_immutable_json(result_path, result)
    return result


def _database_details(path: Path) -> dict[str, Any]:
    uri = f"file:{path.resolve()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as database:
        integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise BackupVerificationError(f"SQLite integrity_check returned {integrity!r}")
        tables = [row[0] for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        counts = {table: database.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] for table in tables}
        migration_version = None
        if "schema_migrations" in tables:
            migration_version = database.execute("SELECT max(version) FROM schema_migrations").fetchone()[0]
    return {"integrity_check": integrity, "schema_migration_version": migration_version, "table_row_counts": counts}


def _refuse_restore_target(target: Path, backup: Path, source: str | Path | None) -> None:
    target_resolved = target.resolve(strict=False)
    forbidden = [backup.resolve()]
    if source is not None:
        forbidden.append(Path(source).resolve(strict=False))
    if target_resolved in forbidden:
        raise BackupSafetyError("verification destination must not be the backup or source path")
    lowered = str(target_resolved).lower()
    if any(marker in lowered for marker in _PRODUCTION_MARKERS):
        raise BackupSafetyError("verification destination looks production-like; use a new isolated temporary path")


def _existing_file(path: str | Path, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_file():
        raise BackupSafetyError(f"{label} must be an existing regular file: {candidate}")
    return candidate


def _require_new_file(path: Path, label: str) -> None:
    if path.exists():
        raise BackupSafetyError(f"{label} already exists; refusing overwrite: {path}")


def _require_nonempty_watermark(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise BackupSafetyError("source watermark must be explicitly supplied and non-empty")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupVerificationError(f"cannot read backup manifest: {exc}") from exc
    if not isinstance(loaded, dict) or loaded.get("format") != "seer-sqlite-backup-manifest/v1":
        raise BackupVerificationError("backup manifest has an unrecognised format")
    return loaded


def _write_immutable_json(path: Path, value: dict[str, Any]) -> None:
    _require_new_file(path, "manifest destination")
    path.parent.mkdir(parents=True, exist_ok=True)
    # x prevents a time-of-check/time-of-use overwrite race.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o444)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main(argv: Sequence[str] | None = None) -> int:
    """Backup then independently verify it; all paths are explicit and new."""
    arguments = list(argv) if argv is not None else None
    if arguments is not None and any(option in arguments for option in _DESTRUCTIVE_OPTIONS):
        raise SystemExit("destructive/cutover options are not supported")
    parser = argparse.ArgumentParser(description="Create and verify a non-destructive SEER SQLite backup")
    parser.add_argument("--source", required=True)
    parser.add_argument("--backup-destination", required=True)
    parser.add_argument("--manifest-destination", required=True)
    parser.add_argument("--source-watermark", required=True)
    parser.add_argument("--verification-destination", required=True)
    parser.add_argument("--verification-manifest-destination", required=True)
    parsed = parser.parse_args(arguments)
    if any(option in _DESTRUCTIVE_OPTIONS for option in os.sys.argv[1:] if arguments is None):
        parser.error("destructive/cutover options are not supported")
    manifest = create_backup(
        source=parsed.source, backup_destination=parsed.backup_destination,
        manifest_destination=parsed.manifest_destination, source_watermark=parsed.source_watermark,
    )
    result = verify_backup(
        backup=parsed.backup_destination, backup_manifest=parsed.manifest_destination,
        verification_destination=parsed.verification_destination,
        verification_manifest_destination=parsed.verification_manifest_destination,
        source_path=parsed.source,
    )
    print(json.dumps({"backup_manifest": manifest, "verification": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    main()
