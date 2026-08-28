"""Focused safety tests for the SEER SQLite backup/restore utility."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from contextlib import closing
import unittest
from pathlib import Path

from seer_finance.ledger.backup_restore import (
    BackupSafetyError,
    BackupVerificationError,
    create_backup,
    main,
    verify_backup,
)


class BackupRestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source = self.root / "source.sqlite3"
        with closing(sqlite3.connect(self.source)) as database:
            database.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY)")
            database.execute("INSERT INTO schema_migrations VALUES (2)")
            database.execute("CREATE TABLE expenses (expense_id TEXT PRIMARY KEY, amount_pence INTEGER)")
            database.executemany("INSERT INTO expenses VALUES (?, ?)", [("one", 100), ("two", 250)])
            database.commit()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _paths(self) -> tuple[Path, Path, Path, Path]:
        return (self.root / "backup.sqlite3", self.root / "backup.manifest.json",
                self.root / "restore.sqlite3", self.root / "restore.manifest.json")

    def _backup(self) -> tuple[Path, Path, Path, Path, dict]:
        backup, manifest, restore, result = self._paths()
        created = create_backup(
            source=self.source, backup_destination=backup, manifest_destination=manifest,
            source_watermark="telegram:message:123",
        )
        return backup, manifest, restore, result, created

    def test_consistent_backup_round_trip_and_read_only_verification(self) -> None:
        backup, manifest, restore, result, _ = self._backup()
        verified = verify_backup(
            backup=backup, backup_manifest=manifest, verification_destination=restore,
            verification_manifest_destination=result, source_path=self.source,
        )
        self.assertEqual("passed", verified["status"])
        self.assertEqual("ok", verified["integrity_check"])
        self.assertEqual({"expenses": 2, "schema_migrations": 1},
                         verified["observed_database_details"]["table_row_counts"])
        with closing(sqlite3.connect(f"file:{restore}?mode=ro", uri=True)) as database:
            self.assertEqual(2, database.execute("SELECT count(*) FROM expenses").fetchone()[0])

    def test_refuses_backup_or_manifest_overwrite(self) -> None:
        backup, manifest, _, _, _ = self._backup()
        with self.assertRaises(BackupSafetyError):
            create_backup(source=self.source, backup_destination=backup, manifest_destination=self.root / "new.json",
                          source_watermark="watermark")
        with self.assertRaises(BackupSafetyError):
            create_backup(source=self.source, backup_destination=self.root / "new.sqlite3", manifest_destination=manifest,
                          source_watermark="watermark")

    def test_manifest_has_checksums_version_watermark_and_safe_source_checksum_label(self) -> None:
        _, manifest_path, _, _, manifest = self._backup()
        on_disk = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest, on_disk)
        self.assertEqual("seer-sqlite-backup-manifest/v1", on_disk["format"])
        self.assertEqual(str(self.source), on_disk["source_path_as_supplied"])
        self.assertEqual("telegram:message:123", on_disk["source_watermark"])
        self.assertEqual(2, on_disk["schema_migration_version"])
        self.assertEqual(64, len(on_disk["backup_sha256"]))
        self.assertEqual(64, len(on_disk["source_sha256"]))
        self.assertIn("not a point-in-time consistency proof", on_disk["source_sha256_scope"])
        self.assertFalse(manifest_path.stat().st_mode & 0o222)

    def test_corrupt_backup_fails_verification_and_records_failure(self) -> None:
        backup, manifest, restore, result, _ = self._backup()
        with backup.open("ab") as handle:
            handle.write(b"corruption")
        with self.assertRaises(BackupVerificationError):
            verify_backup(backup=backup, backup_manifest=manifest, verification_destination=restore,
                          verification_manifest_destination=result, source_path=self.source)
        recorded = json.loads(result.read_text(encoding="utf-8"))
        self.assertEqual("failed", recorded["status"])
        self.assertIn("checksum", recorded["error"])

    def test_refuses_existing_or_production_looking_restore_target(self) -> None:
        backup, manifest, _, result, _ = self._backup()
        with self.assertRaises(BackupSafetyError):
            verify_backup(backup=backup, backup_manifest=manifest, verification_destination=backup,
                          verification_manifest_destination=result, source_path=self.source)
        with self.assertRaises(BackupSafetyError):
            verify_backup(backup=backup, backup_manifest=manifest,
                          verification_destination=self.root / "production-restore.sqlite3",
                          verification_manifest_destination=self.root / "production-restore.json", source_path=self.source)

    def test_cli_rejects_destructive_or_cutover_options(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            main(["--source", str(self.source), "--backup-destination", str(self.root / "b.sqlite3"),
                  "--manifest-destination", str(self.root / "b.json"), "--source-watermark", "w",
                  "--verification-destination", str(self.root / "v.sqlite3"),
                  "--verification-manifest-destination", str(self.root / "v.json"), "--cutover"])
        self.assertIn("destructive/cutover", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
