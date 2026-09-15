from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from seer_finance.ledger.expense_capture_adapter import capture_candidate
from seer_finance.ledger.expense_repository import ExpenseRepository
from seer_finance.ledger.schema import Category, Direction, Transaction
from seer_finance.ledger.sharepoint_contract import (
    EXPENSE_LEDGER_PATH,
    FINANCE_LEDGER_PATH,
    SharePointCacheUnavailable,
    SharePointMutationBlocked,
    SharePointRebaseRequired,
    SharePointWritePending,
)
from seer_finance.ledger.sharepoint_finance_writer import SharePointFinanceWriter
from seer_finance.sharepoint_boundary import SharePointBoundary
from seer_finance.ledger.workbook_codec import WorkbookCodec


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
        self.initial = self._workbook([])
        self.initial_hash = hashlib.sha256(self.initial).hexdigest()
        self._cache_workbook(self.initial)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _workbook(transactions: list[dict]) -> bytes:
        return WorkbookCodec.encode_finance({
            "schema_version": 1,
            "transactions": transactions,
        })

    def _cache_workbook(
        self,
        content: bytes,
        *,
        etag: str = "etag-0",
        version: str = "v0",
    ) -> None:
        destination = self.cache / "Finance" / "Finance ledger.xlsx"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        digest = hashlib.sha256(content).hexdigest()
        semantic = WorkbookCodec.semantic_hash(content)
        (self.cache / ".manifest.json").write_text(
            json.dumps({
                "synced_at": now,
                "cached": {
                    "Finance/Finance ledger.xlsx": {
                        "sp_path": FINANCE_LEDGER_PATH,
                        "etag": etag,
                        "version": version,
                        "synced_at": now,
                        "content_sha256": digest,
                        "semantic_sha256": semantic,
                    }
                },
            }),
            encoding="utf-8",
        )

    def _operation(self) -> dict:
        return json.loads(self.queue.read_text(encoding="utf-8"))[0]

    def _queue_workbook(self, content: bytes) -> None:
        snapshot = self.writer.store.read_workbook_snapshot(FINANCE_LEDGER_PATH)
        with self.assertRaises(SharePointWritePending):
            self.writer.store.write_workbook(
                path=FINANCE_LEDGER_PATH,
                content_base64=base64.b64encode(content).decode("ascii"),
                content_sha256=hashlib.sha256(content).hexdigest(),
                base_etag=snapshot["etag"],
                expected_source_sha256=snapshot["content_sha256"],
                expected_snapshot=snapshot,
                semantic_workbook_sha256=WorkbookCodec.semantic_hash(content),
            )

    def _retry_operation(self, operation: dict) -> str:
        snapshot = self.writer.store.read_workbook_snapshot(FINANCE_LEDGER_PATH)
        return self.writer.store.write_workbook(
            path=FINANCE_LEDGER_PATH,
            content_base64=operation["content_base64"],
            content_sha256=operation["content_sha256"],
            base_etag=snapshot["etag"],
            expected_source_sha256=snapshot["content_sha256"],
            expected_snapshot=snapshot,
            semantic_workbook_sha256=operation["semantic_workbook_sha256"],
        )

    @staticmethod
    def _proof(operation: dict, **overrides: object) -> dict:
        proof = {
            "id": operation["id"],
            "path": FINANCE_LEDGER_PATH,
            "success": True,
            "processed_at": "2026-08-10T00:00:00Z",
            "resulting_etag": "etag-1",
            "resulting_version": "v1",
            "readback_sha256": operation["content_sha256"],
            "readback_semantic_workbook_sha256": (
                operation["semantic_workbook_sha256"]
            ),
        }
        proof.update(overrides)
        return proof

    def test_defaults_target_canonical_finance_path_and_fail_closed(self) -> None:
        for path in (
            self.cache / "Finance" / "Finance ledger.xlsx",
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
        operation = self._operation()
        desired = base64.b64decode(operation["content_base64"])
        self.results.write_text(
            json.dumps([self._proof(operation)]),
            encoding="utf-8",
        )
        with self.assertRaises(SharePointWritePending):
            self.writer.validate_and_write(self.transaction)
        self._cache_workbook(desired, etag="etag-1", version="v1")
        self.assertEqual(
            "sharepoint:expense-1",
            self.writer.validate_and_write(self.transaction),
        )

    def test_legacy_bare_success_and_wrong_proof_are_not_completion(self) -> None:
        with self.assertRaises(SharePointWritePending):
            self.writer.validate_and_write(self.transaction)
        operation = self._operation()
        desired = base64.b64decode(operation["content_base64"])
        self._cache_workbook(desired, etag="etag-1", version="v1")
        proof = self._proof(operation)
        for mutation in (
            {
                "id": operation["id"],
                "path": FINANCE_LEDGER_PATH,
                "success": True,
                "processed_at": "2026-08-10T00:00:00Z",
            },
            {**proof, "path": "/wrong/path.xlsx"},
            {**proof, "readback_sha256": "bad"},
            {**proof, "readback_semantic_workbook_sha256": "bad"},
            {**proof, "resulting_etag": "wrong"},
            {**proof, "resulting_version": "wrong"},
        ):
            self.results.write_text(json.dumps([mutation]), encoding="utf-8")
            with self.assertRaises(SharePointWritePending):
                self._retry_operation(operation)
        self.results.write_text(json.dumps([proof]), encoding="utf-8")
        self.assertEqual(operation["id"], self._retry_operation(operation))

    def test_expense_path_is_not_finance_path(self) -> None:
        self.assertEqual("/Expenses/Expense ledger.xlsx", EXPENSE_LEDGER_PATH)
        self.assertNotEqual(EXPENSE_LEDGER_PATH, FINANCE_LEDGER_PATH)

    def test_public_boundary_prohibits_canonical_append(self) -> None:
        result = SharePointBoundary(store=self.writer.store).write_verified(
            FINANCE_LEDGER_PATH, "append payload", operation="append"
        )
        self.assertFalse(result.accepted)
        self.assertFalse(result.verified)
        self.assertIn("prohibit append", result.blocker or "")
        self.assertFalse(self.queue.exists())

    def test_receipt_boundary_accepts_the_upload_cli_json_proof(self) -> None:
        receipt = Path(self.temp.name) / "receipt.pdf"
        receipt.write_bytes(b"receipt bytes")
        digest = hashlib.sha256(receipt.read_bytes()).hexdigest()
        path = f"/Expenses/Receipts/{digest}-receipt.pdf"
        boundary = SharePointBoundary(store=self.writer.store)

        pending = boundary.upload_receipt_verified(
            path=path,
            source_ref="email:receipt-proof",
            local_path=str(receipt),
            content_sha256=digest,
            mime_type="application/pdf",
        )
        self.assertTrue(pending.accepted)
        self.assertFalse(pending.verified)
        operation = json.loads(self.queue.read_text(encoding="utf-8"))[0]
        self.assertEqual("upload_binary", operation["operation"])
        self.assertEqual(path, operation["path"])

        result = {
            "id": operation["id"],
            "operation": "upload_binary",
            "path": path,
            "success": True,
            "processed_at": "2026-08-10T00:00:00Z",
            "output": json.dumps({
                "status": "uploaded",
                "path": path,
                "url": "https://example.invalid/receipt.pdf",
                "etag": '"receipt-v1"',
                "size": receipt.stat().st_size,
                "mime_type": "application/pdf",
                "content_sha256": digest,
                "readback_sha256": "bad",
            }, sort_keys=True),
        }
        self.results.write_text(json.dumps([result]), encoding="utf-8")
        rejected = boundary.upload_receipt_verified(
            path=path,
            source_ref="email:receipt-proof",
            local_path=str(receipt),
            content_sha256=digest,
            mime_type="application/pdf",
        )
        self.assertTrue(rejected.accepted)
        self.assertFalse(rejected.verified)
        result["output"] = json.dumps({
            "status": "uploaded",
            "path": path,
            "url": "https://example.invalid/receipt.pdf",
            "etag": '"receipt-v1"',
            "size": receipt.stat().st_size,
            "mime_type": "application/pdf",
            "content_sha256": digest,
            "readback_sha256": digest,
        }, sort_keys=True)
        self.results.write_text(json.dumps([result]), encoding="utf-8")
        verified = boundary.upload_receipt_verified(
            path=path,
            source_ref="email:receipt-proof",
            local_path=str(receipt),
            content_sha256=digest,
            mime_type="application/pdf",
        )
        self.assertTrue(verified.complete)
        self.assertEqual(f'{path}#"receipt-v1"', verified.canonical_ref)

    def test_receipt_cli_processor_store_blocks_wrong_remote_bytes_for_exists_and_upload(
        self,
    ) -> None:
        microsoft_root = (
            Path(__file__).resolve().parents[3]
            / "attached_assets"
            / "integrations"
            / "microsoft"
        )

        def load_module(name: str, filename: str):
            spec = importlib.util.spec_from_file_location(name, microsoft_root / filename)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        queue_processor = load_module(
            "receipt_chain_queue_processor",
            "sharepoint_queue_processor.py",
        )
        sharepoint = load_module("receipt_chain_sharepoint", "sharepoint.py")

        class Response:
            def __init__(
                self,
                *,
                status_code: int = 200,
                payload: dict | None = None,
                content: bytes = b"",
            ) -> None:
                self.status_code = status_code
                self._payload = payload or {}
                self.content = content
                self.text = content.decode("utf-8", errors="replace")

            @property
            def ok(self) -> bool:
                return 200 <= self.status_code < 300

            def json(self) -> dict:
                return self._payload

        old_paths = {
            name: getattr(queue_processor, name)
            for name in (
                "QUEUE_FILE",
                "LOCK_FILE",
                "RESULT_JSON",
                "RESULT_MD",
                "LOG_FILE",
                "WORKSPACE",
                "SP_SCRIPT",
            )
        }
        try:
            for mode in ("exists", "uploaded"):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    queue = root / "queue.json"
                    results = root / "results.json"
                    source = root / "receipt.pdf"
                    source.write_bytes(b"receipt bytes")
                    remote_wrong = b"wrong remote bytes"
                    digest = hashlib.sha256(source.read_bytes()).hexdigest()
                    path = f"/Expenses/Receipts/{digest}-receipt.pdf"
                    script = root / "sharepoint.py"
                    script.write_text("# test fixture", encoding="utf-8")
                    cache = root / "cache"
                    store = self.writer.store.__class__(
                        queue_path=queue,
                        results_path=results,
                        cache_root=cache,
                    )
                    with self.assertRaises(SharePointWritePending):
                        store.upload_binary(
                            path=path,
                            source_path=source,
                            content_sha256=digest,
                            mime_type="application/pdf",
                        )

                    queue_processor.QUEUE_FILE = queue
                    queue_processor.LOCK_FILE = root / "queue.lock"
                    queue_processor.RESULT_JSON = results
                    queue_processor.RESULT_MD = root / "results.md"
                    queue_processor.LOG_FILE = root / "queue.log"
                    queue_processor.WORKSPACE = root / "workspace"
                    queue_processor.SP_SCRIPT = script

                    metadata = Response(payload={
                        "eTag": '"receipt-v1"',
                        "size": len(remote_wrong),
                        "webUrl": "https://example.invalid/receipt.pdf",
                    })
                    if mode == "exists":
                        gets = [
                            Response(
                                payload={
                                    "eTag": '"receipt-v1"',
                                    "size": len(remote_wrong),
                                    "webUrl": "https://example.invalid/receipt.pdf",
                                }
                            ),
                            Response(content=remote_wrong),
                        ]
                        puts: list[Response] = []
                    else:
                        gets = [
                            Response(status_code=404),
                            Response(content=remote_wrong),
                        ]
                        puts = [metadata]

                    def invoke_cli(
                        command: list[str],
                        *,
                        capture_output: bool,
                        text: bool,
                        timeout: int,
                    ) -> subprocess.CompletedProcess[str]:
                        del capture_output, text, timeout
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        try:
                            with (
                                redirect_stdout(stdout),
                                redirect_stderr(stderr),
                                patch.object(
                                    sharepoint.requests,
                                    "get",
                                    side_effect=gets,
                                ),
                                patch.object(
                                    sharepoint.requests,
                                    "put",
                                    side_effect=puts,
                                ),
                            ):
                                sharepoint.cmd_upload(
                                    "token",
                                    command[3],
                                    "site",
                                    "drive",
                                    command[5],
                                    command[7],
                                )
                        except SystemExit as exc:
                            code = int(exc.code or 0)
                        else:
                            code = 0
                        return subprocess.CompletedProcess(
                            command,
                            code,
                            stdout=stdout.getvalue(),
                            stderr=stderr.getvalue(),
                        )

                    with patch.object(
                        queue_processor.subprocess,
                        "run",
                        side_effect=invoke_cli,
                    ):
                        queue_processor.main()

                    processor_result = json.loads(
                        results.read_text(encoding="utf-8")
                    )[0]
                    self.assertFalse(processor_result["success"], mode)
                    self.assertIn("readback mismatch", processor_result["output"])
                    with self.assertRaises(SharePointWritePending):
                        store.upload_binary(
                            path=path,
                            source_path=source,
                            content_sha256=digest,
                            mime_type="application/pdf",
                        )
                    self.assertEqual(
                        1,
                        len(json.loads(queue.read_text(encoding="utf-8"))),
                    )
        finally:
            for name, value in old_paths.items():
                setattr(queue_processor, name, value)

    def test_cache_preserves_exact_workbook_bytes_and_unicode_cells(self) -> None:
        content = self._workbook([{
            "txn_id": "unicode-1",
            "date": "2026-08-10",
            "direction": "expense",
            "amount_pence": 1200,
            "description": "προσθήκη — €",
            "counterparty": "Café",
            "category": "software",
            "pre_trading": False,
            "tax_treatment": None,
            "source_ref": "email:unicode",
        }])
        self._cache_workbook(content)
        snapshot = self.writer.store.read_workbook_snapshot(FINANCE_LEDGER_PATH)
        self.assertEqual(content, snapshot["content_bytes"])
        self.assertEqual(
            hashlib.sha256(content).hexdigest(),
            snapshot["content_sha256"],
        )
        self.assertEqual(
            "προσθήκη — €",
            WorkbookCodec.decode_finance(snapshot["content_bytes"])["transactions"][0][
                "description"
            ],
        )

    def test_canonical_create_requires_separately_gated_bootstrap(self) -> None:
        for path in (
            self.cache / "Finance" / "Finance ledger.xlsx",
            self.cache / ".manifest.json",
        ):
            path.unlink()
        old_gate = os.environ.pop("SEER_FINANCE_ALLOW_BOOTSTRAP", None)
        try:
            with self.assertRaises(SharePointCacheUnavailable):
                self.writer.store.bootstrap(
                    path=FINANCE_LEDGER_PATH,
                    content=base64.b64encode(self.initial).decode("ascii"),
                )
        finally:
            if old_gate is not None:
                os.environ["SEER_FINANCE_ALLOW_BOOTSTRAP"] = old_gate
        self.assertFalse(self.queue.exists())

    def test_queue_enqueue_preserves_concurrent_producers(self) -> None:
        def enqueue(index: int) -> None:
            content = self._workbook([{"txn_id": f"txn-{index}"}])
            try:
                self.writer.store.write_workbook(
                    path=FINANCE_LEDGER_PATH,
                    content_base64=base64.b64encode(content).decode("ascii"),
                    content_sha256=hashlib.sha256(content).hexdigest(),
                    base_etag="etag-0",
                    expected_source_sha256=self.initial_hash,
                    semantic_workbook_sha256=WorkbookCodec.semantic_hash(content),
                )
            except SharePointWritePending:
                return

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(enqueue, range(8)))
        queued = json.loads(self.queue.read_text(encoding="utf-8"))
        self.assertEqual(1, len({item["id"] for item in queued}))
        self.assertEqual(1, len(self.writer.store._read_journal()))

    def test_initialized_document_is_read_before_appending(self) -> None:
        initial = self._workbook([{
            "txn_id": "existing",
            "date": "2026-08-01",
            "direction": "expense",
            "amount_pence": 500,
            "description": "Existing",
            "counterparty": "Acme",
            "category": "software",
            "pre_trading": False,
            "tax_treatment": None,
            "source_ref": "email:existing",
        }])
        self._cache_workbook(initial)

        with self.assertRaises(SharePointWritePending):
            self.writer.validate_and_write(self.transaction)
        queued = self._operation()
        self.assertNotIn("content", queued)
        decoded = WorkbookCodec.decode_finance(
            base64.b64decode(queued["content_base64"])
        )
        self.assertEqual(
            ["existing", "expense-1"],
            [row["txn_id"] for row in decoded["transactions"]],
        )

    def test_stale_or_unverifiable_manifest_never_becomes_a_base(self) -> None:
        manifest = json.loads(
            (self.cache / ".manifest.json").read_text(encoding="utf-8")
        )
        manifest["cached"]["Finance/Finance ledger.xlsx"]["etag"] = ""
        (self.cache / ".manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        with self.assertRaises(SharePointCacheUnavailable) as caught:
            self.writer.validate_and_write(self.transaction)
        self.assertIn("etag/version", str(caught.exception))
        self.assertFalse(self.queue.exists())

    def test_initialized_unknown_schema_is_blocked_not_converted_silently(self) -> None:
        unknown_schema = WorkbookCodec.encode_finance({
            "schema_version": 0,
            "transactions": [],
        })
        self._cache_workbook(unknown_schema)
        with self.assertRaises(ValueError):
            self.writer.validate_and_write(self.transaction)
        self.assertFalse(self.queue.exists())

    def test_evicted_old_result_cannot_drive_a_new_whole_document_update(self) -> None:
        with self.assertRaises(SharePointWritePending):
            self.writer.validate_and_write(self.transaction)
        operation = self._operation()
        desired = base64.b64decode(operation["content_base64"])
        self.assertEqual("etag-0", operation["base_etag"])
        self.assertEqual("v0", operation["base_version"])
        self.assertEqual(
            operation["base_content_sha256"],
            operation["expected_source_sha256"],
        )
        self.assertEqual(
            operation["base_content_sha256"],
            hashlib.sha256(self.initial).hexdigest(),
        )
        self.assertEqual(
            operation["content_sha256"],
            hashlib.sha256(desired).hexdigest(),
        )
        self._cache_workbook(desired, etag="etag-1", version="v1")
        self.results.write_text(
            json.dumps([
                {
                    "id": f"other-{index}",
                    "success": True,
                    "processed_at": "2026-08-10T00:00:00Z",
                }
                for index in range(1001)
            ]),
            encoding="utf-8",
        )
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
        desired = self._workbook([{"txn_id": "source-fact"}])
        self._queue_workbook(desired)
        operation = self._operation()
        self.results.write_text(
            json.dumps([{
                "id": operation["id"],
                "path": FINANCE_LEDGER_PATH,
                "success": False,
                "processed_at": "2026-08-10T00:00:00Z",
                "error_code": "rebase_required",
                "rebase_required": True,
                "resulting_etag": "etag-remote",
                "resulting_version": "v2",
            }]),
            encoding="utf-8",
        )
        with self.assertRaises(SharePointRebaseRequired):
            self._retry_operation(operation)
        journal = json.loads(self.writer.store.journal_path.read_text())
        self.assertEqual("rebase_required", journal[-1]["state"])
        self.assertEqual([], json.loads(self.queue.read_text(encoding="utf-8")))
        with self.assertRaises(SharePointRebaseRequired):
            self._retry_operation(operation)
        self.assertEqual([], json.loads(self.queue.read_text(encoding="utf-8")))
        fresh = self._workbook([{"txn_id": "remote-fact"}])
        self._cache_workbook(fresh, etag="etag-remote", version="v2")
        self._queue_workbook(desired)
        rebased = self._operation()
        self.assertEqual("etag-remote", rebased["base_etag"])
        self.assertEqual("v2", rebased["base_version"])
        self.assertEqual(
            desired,
            base64.b64decode(rebased["content_base64"]),
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