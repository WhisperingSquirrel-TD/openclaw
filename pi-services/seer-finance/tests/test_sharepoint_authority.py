from __future__ import annotations

import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from seer_finance.ledger.expense_repository import ExpenseRepository
from seer_finance.ledger.expense_capture_adapter import capture_candidate
from seer_finance.ledger.sharepoint_contract import cache_body, document_content
from seer_finance.ledger.schema import Category, Direction, Transaction
from seer_finance.ledger.sharepoint_contract import (
    FINANCE_LEDGER_PATH,
    EXPENSE_LEDGER_PATH,
    SharePointCacheUnavailable,
    SharePointMutationBlocked,
    SharePointRebaseRequired,
    SharePointWritePending,
)
from seer_finance.sharepoint_boundary import SharePointBoundary
from seer_finance.ledger.sharepoint_finance_writer import SharePointFinanceWriter


class SharePointAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.queue = root / "sharepoint-queue.json"
        self.results = root / "sharepoint-queue-results.json"
        self.cache = root / "sharepoint-cache"
        self.writer = SharePointFinanceWriter(
            queue_path=self.queue,
            results_path=self.results,
            cache_root=self.cache,
        )
        self.transaction = Transaction(
            "expense-1", "2026-08-10", Direction.EXPENSE, 1200,
            "Test expense", "Acme", Category.SOFTWARE, source_ref="email:1",
        )
        self._cache_document(document_content("Finance ledger", {
            "schema_version": 1, "transactions": [],
        }))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_defaults_target_canonical_finance_path_and_fail_closed(self) -> None:
        for path in (
            self.cache / "Finance" / "Finance ledger.md",
            self.cache / ".manifest.json",
        ):
            path.unlink()
        with self.assertRaises(SharePointCacheUnavailable) as caught:
            self.writer.validate_and_write(self.transaction)
        self.assertIn("cache", str(caught.exception))
        self.assertFalse(self.queue.exists())

    def test_processed_success_requires_exact_cache_readback(self) -> None:
        with self.assertRaises(SharePointWritePending):
            self.writer.validate_and_write(self.transaction)
        operation = json.loads(self.queue.read_text(encoding="utf-8"))[0]
        self.results.write_text(json.dumps([{
            "id": operation["id"], "path": FINANCE_LEDGER_PATH, "success": True,
            "processed_at": "2026-08-10T00:00:00Z",
            "resulting_etag": "etag-1", "resulting_version": "v1",
            "readback_sha256": hashlib.sha256(
                operation["content"].encode("utf-8")
            ).hexdigest(),
        }]), encoding="utf-8")
        with self.assertRaises(SharePointWritePending):
            self.writer.validate_and_write(self.transaction)
        cache_path = self.cache / "Finance" / "Finance ledger.md"
        self._cache_document(operation["content"], etag="etag-1", version="v1")
        self.assertEqual("sharepoint:expense-1", self.writer.validate_and_write(self.transaction))

    def test_legacy_bare_success_and_wrong_proof_are_not_completion(self) -> None:
        with self.assertRaises(SharePointWritePending):
            self.writer.validate_and_write(self.transaction)
        operation = json.loads(self.queue.read_text(encoding="utf-8"))[0]
        proof = {
            "id": operation["id"], "path": FINANCE_LEDGER_PATH, "success": True,
            "processed_at": "2026-08-10T00:00:00Z",
            "resulting_etag": "etag-1", "resulting_version": "v1",
            "readback_sha256": hashlib.sha256(
                operation["content"].encode("utf-8")
            ).hexdigest(),
        }
        for mutation in (
            {"id": operation["id"], "path": FINANCE_LEDGER_PATH, "success": True,
             "processed_at": "2026-08-10T00:00:00Z"},
            {**proof, "path": "/wrong/path.md"},
            {**proof, "readback_sha256": "bad"},
            {**proof, "resulting_etag": "wrong"},
            {**proof, "resulting_version": "wrong"},
        ):
            self.results.write_text(json.dumps([mutation]), encoding="utf-8")
            self._cache_document(operation["content"], etag="etag-1", version="v1")
            with self.assertRaises(SharePointWritePending):
                self.writer.store.write(
                    path=FINANCE_LEDGER_PATH, content=operation["content"]
                )
        self.results.write_text(json.dumps([proof]), encoding="utf-8")
        self.assertEqual(
            operation["id"],
            self.writer.store.write(path=FINANCE_LEDGER_PATH, content=operation["content"]),
        )

    def test_expense_path_is_not_finance_path(self) -> None:
        self.assertEqual("/Expenses/Expense ledger.md", EXPENSE_LEDGER_PATH)
        self.assertNotEqual(EXPENSE_LEDGER_PATH, FINANCE_LEDGER_PATH)

    def test_public_boundary_prohibits_canonical_append(self) -> None:
        result = SharePointBoundary(store=self.writer.store).write_verified(
            FINANCE_LEDGER_PATH, "append payload", operation="append"
        )
        self.assertFalse(result.accepted)
        self.assertFalse(result.verified)
        self.assertIn("prohibit append", result.blocker or "")
        self.assertFalse(self.queue.exists())

    def test_cache_header_removal_preserves_leading_blanks_and_unicode_bytes(self) -> None:
        content = "\n\n# Finance ledger\n\nπροσθήκη — €\n"
        raw = "<!-- sharepoint-cache: /Finance/Finance ledger.md | synced: 2026-08-10T00:00:00Z -->\n\n" + content
        self.assertEqual(content, cache_body(raw))
        self._cache_document(content)
        destination = self.cache / "Finance" / "Finance ledger.md"
        destination.write_text(raw, encoding="utf-8")
        snapshot = self.writer.store.read_snapshot(FINANCE_LEDGER_PATH)
        self.assertEqual(content, snapshot["content"])
        self.assertEqual(
            hashlib.sha256(content.encode("utf-8")).hexdigest(),
            snapshot["content_sha256"],
        )

    def test_canonical_create_requires_separately_gated_bootstrap(self) -> None:
        for path in (
            self.cache / "Finance" / "Finance ledger.md",
            self.cache / ".manifest.json",
        ):
            path.unlink()
        old_gate = os.environ.pop("SEER_FINANCE_ALLOW_BOOTSTRAP", None)
        try:
            with self.assertRaises(SharePointCacheUnavailable):
                self.writer.store.bootstrap(
                    path=FINANCE_LEDGER_PATH,
                    content=document_content("Finance ledger", {
                        "schema_version": 1, "transactions": [],
                    }),
                )
        finally:
            if old_gate is not None:
                os.environ["SEER_FINANCE_ALLOW_BOOTSTRAP"] = old_gate
        self.assertFalse(self.queue.exists())

    def test_queue_enqueue_preserves_concurrent_producers(self) -> None:
        def enqueue(index: int) -> None:
            try:
                self.writer.store.write(
                    path=FINANCE_LEDGER_PATH,
                    content=document_content("Finance ledger", {
                        "schema_version": 1, "transactions": [{"txn_id": f"txn-{index}"}],
                    }),
                )
            except SharePointWritePending:
                return

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(enqueue, range(8)))
        queued = json.loads(self.queue.read_text(encoding="utf-8"))
        self.assertEqual(1, len({item["id"] for item in queued}))
        self.assertEqual(1, len(self.writer.store._read_journal()))

    def test_initialized_document_is_read_before_appending(self) -> None:
        initial = {
            "schema_version": 1,
            "transactions": [{
                "txn_id": "existing", "date": "2026-08-01", "direction": "expense",
                "amount_pence": 500, "description": "Existing", "counterparty": "Acme",
                "category": "software", "pre_trading": False, "tax_treatment": None,
                "source_ref": "email:existing",
            }],
        }
        self._cache_document(document_content("Finance ledger", initial))

        with self.assertRaises(SharePointWritePending):
            self.writer.validate_and_write(self.transaction)
        queued = json.loads(self.queue.read_text(encoding="utf-8"))
        self.assertIn('"txn_id":"existing"', queued[0]["content"])
        self.assertIn('"txn_id":"expense-1"', queued[0]["content"])

    def test_stale_or_unverifiable_manifest_never_becomes_a_base(self) -> None:
        manifest = json.loads((self.cache / ".manifest.json").read_text(encoding="utf-8"))
        manifest["cached"]["Finance/Finance ledger.md"]["etag"] = ""
        (self.cache / ".manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(SharePointCacheUnavailable) as caught:
            self.writer.validate_and_write(self.transaction)
        self.assertIn("etag/version", str(caught.exception))
        self.assertFalse(self.queue.exists())

    def test_initialized_unknown_schema_is_blocked_not_converted_silently(self) -> None:
        self._cache_document(document_content("Finance ledger", {
            "schema_version": 0, "transactions": [],
        }))
        with self.assertRaises(ValueError):
            self.writer.validate_and_write(self.transaction)
        self.assertFalse(self.queue.exists())

    def test_evicted_old_result_cannot_drive_a_new_whole_document_update(self) -> None:
        with self.assertRaises(SharePointWritePending):
            self.writer.validate_and_write(self.transaction)
        operation = json.loads(self.queue.read_text(encoding="utf-8"))[0]
        self.assertEqual("etag-0", operation["base_etag"])
        self.assertEqual("v0", operation["base_version"])
        self.assertEqual(operation["base_content_sha256"], operation["expected_source_sha256"])
        self.assertEqual(operation["base_content_sha256"], operation["base_content_hash"])
        self.assertEqual(operation["content_sha256"], operation["content_hash"])
        self._cache_document(operation["content"], etag="etag-1", version="v1")
        self.results.write_text(json.dumps([
            {"id": f"other-{index}", "success": True, "processed_at": "2026-08-10T00:00:00Z"}
            for index in range(1001)
        ]), encoding="utf-8")
        next_transaction = Transaction(
            "expense-2", "2026-08-11", Direction.EXPENSE, 1300,
            "Next expense", "Acme", Category.SOFTWARE, source_ref="email:2",
        )
        with self.assertRaises(SharePointMutationBlocked):
            self.writer.validate_and_write(next_transaction)
        self.assertEqual(1, len(json.loads(self.queue.read_text(encoding="utf-8"))))

    def test_dropped_queue_entry_is_recovered_from_durable_journal(self) -> None:
        with self.assertRaises(SharePointWritePending):
            self.writer.validate_and_write(self.transaction)
        self.queue.unlink()
        with self.assertRaises(SharePointWritePending):
            self.writer.validate_and_write(self.transaction)
        recovered = json.loads(self.queue.read_text(encoding="utf-8"))
        self.assertEqual(1, len(recovered))
        self.assertEqual(recovered[0]["base_etag"], "etag-0")
        self.assertEqual(recovered[0]["base_version"], "v0")

    def test_rebase_conflict_retires_stale_mutation_and_retries_on_fresh_cache(self) -> None:
        desired = document_content("Finance ledger", {
            "schema_version": 1, "transactions": [{"txn_id": "source-fact"}],
        })
        with self.assertRaises(SharePointWritePending):
            self.writer.store.write(path=FINANCE_LEDGER_PATH, content=desired)
        operation = json.loads(self.queue.read_text(encoding="utf-8"))[0]
        self.results.write_text(json.dumps([{
            "id": operation["id"], "path": FINANCE_LEDGER_PATH, "success": False,
            "processed_at": "2026-08-10T00:00:00Z", "error_code": "rebase_required",
            "rebase_required": True,
            "resulting_etag": "etag-remote", "resulting_version": "v2",
        }]), encoding="utf-8")
        with self.assertRaises(SharePointRebaseRequired):
            self.writer.store.write(path=FINANCE_LEDGER_PATH, content=desired)
        journal = json.loads(self.writer.store.journal_path.read_text(encoding="utf-8"))
        self.assertEqual("rebase_required", journal[-1]["state"])
        self.assertEqual([], json.loads(self.queue.read_text(encoding="utf-8")))
        with self.assertRaises(SharePointRebaseRequired):
            self.writer.store.write(path=FINANCE_LEDGER_PATH, content=desired)
        self.assertEqual([], json.loads(self.queue.read_text(encoding="utf-8")))
        fresh = document_content("Finance ledger", {
            "schema_version": 1, "transactions": [{"txn_id": "remote-fact"}],
        })
        self._cache_document(fresh, etag="etag-remote", version="v2")
        with self.assertRaises(SharePointWritePending):
            self.writer.store.write(path=FINANCE_LEDGER_PATH, content=desired)
        rebased = json.loads(self.queue.read_text(encoding="utf-8"))[0]
        self.assertEqual("etag-remote", rebased["base_etag"])
        self.assertEqual("v2", rebased["base_version"])
        self.assertEqual(desired, rebased["content"])

    def _cache_document(self, content: str, *, etag: str = "etag-0", version: str = "v0") -> None:
        destination = self.cache / "Finance" / "Finance ledger.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        manifest = {
            "synced_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "cached": {
                "Finance/Finance ledger.md": {
                    "sp_path": "/Finance/Finance ledger.md",
                    "etag": etag,
                    "version": version,
                    "synced_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "content_sha256": digest,
                }
            },
        }
        (self.cache / ".manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def test_sqlite_is_explicit_migration_state_not_the_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "migration.sqlite3"
            result = capture_candidate(
                source_surface="migration", source_ref="legacy:1",
                facts={"amount_pence": 100}, database=database,
                replay_path=Path(directory) / "replay.json",
            )
            self.assertEqual("captured", result.outcome)
            repository = ExpenseRepository(database)
            try:
                versions = repository.connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                ).fetchall()
                self.assertEqual([1, 2, 3, 4], [row[0] for row in versions])
            finally:
                repository.close()


if __name__ == "__main__":
    unittest.main()