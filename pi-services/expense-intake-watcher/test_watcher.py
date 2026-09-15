#!/usr/bin/env python3
"""Focused regression tests for expense reference extraction/deduplication."""
from __future__ import annotations

import importlib.util
import sys
import json
import base64
import hashlib
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

SEER_FINANCE_ROOT = Path(__file__).resolve().parents[1] / "seer-finance"
if str(SEER_FINANCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SEER_FINANCE_ROOT))

from sharepoint_boundary import (
    BoundaryResult,
    QueueBoundary,
    SharePointBoundaryError,
    _ReadbackRequiredStore,
    _SeerFinanceBoundaryAdapter,
    write_verified,
)

MODULE_PATH = Path(__file__).with_name("watcher.py")
SPEC = importlib.util.spec_from_file_location("expense_watcher", MODULE_PATH)
assert SPEC and SPEC.loader
WATCHER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = WATCHER
SPEC.loader.exec_module(WATCHER)


class MicrosoftInvoiceReferenceTests(unittest.TestCase):
    def test_extracts_stable_microsoft_invoice_reference(self) -> None:
        refs = WATCHER.extract_refs(
            "Your Microsoft invoice G175174660 is ready",
            "Sign in to review your latest invoice. Review your Microsoft invoice. Your statement is ready.",
        )
        self.assertEqual(refs["invoice"], "G175174660")

    def test_does_not_turn_prose_into_invoice_reference(self) -> None:
        refs = WATCHER.extract_refs(
            "Your Microsoft invoice is ready",
            "Review your Microsoft invoice. Your statement is ready.",
        )
        self.assertIsNone(refs["invoice"])

    def test_new_microsoft_reference_is_not_deduped_by_common_prose(self) -> None:
        refs = WATCHER.extract_refs(
            "Your Microsoft invoice G175174660 is ready",
            "Review your Microsoft invoice. Your statement is ready.",
        )
        existing_ledger = "| 30 Jul 2026 | Microsoft billing | Microsoft | TBC | Your previous statement |"
        self.assertFalse(
            WATCHER.row_exists(
                existing_ledger,
                refs,
                "Your Microsoft invoice G175174660 is ready",
            )
        )


class CentralMirrorExpenseHandoffTests(unittest.TestCase):
    def test_low_value_email_does_not_rewrite_monitored_ledger(self) -> None:
        entry = WATCHER.MailEntry(
            account="microsoft", section="inbox", mailbox_path=Path("fixture.md"),
            subject="Monthly newsletter", party="newsletter@example.com",
            date_str="2026-08-27T10:00:00Z", message_id="newsletter-1", body_preview="General news only.",
        )
        with patch.object(WATCHER, "upsert_monitored") as upsert, patch.object(WATCHER, "remove_monitored") as remove:
            state, summary = WATCHER.default_state(), {"reviewed": 0, "not_needed": 0}
            WATCHER.process_email_entry(state, entry, summary)
        self.assertEqual(summary["reviewed"], 1)
        self.assertEqual(summary["not_needed"], 1)
        self.assertEqual(state["item_states"][WATCHER.mail_key(entry)]["status"], "not_needed")
        upsert.assert_not_called()
        remove.assert_not_called()

    def test_low_value_whatsapp_does_not_rewrite_monitored_ledger(self) -> None:
        entry = WATCHER.WhatsAppEntry(
            timestamp="2026-08-27 10:00", contact="A group contact", text="Good morning!", raw_line="fixture", group="Networking",
        )
        with patch.object(WATCHER, "upsert_monitored") as upsert, patch.object(WATCHER, "remove_monitored") as remove:
            state, summary = WATCHER.default_state(), {"not_needed": 0}
            WATCHER.process_whatsapp_entry(state, entry, summary)
        self.assertEqual(summary["not_needed"], 1)
        self.assertEqual(state["item_states"][entry.key]["status"], "not_needed")
        upsert.assert_not_called()
        remove.assert_not_called()

    def test_external_only_expense_event_gets_canonical_blocker_and_proof_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "mirror-events.json"
            expenses = root / "expense-projection.md"
            monitored = root / "monitored-items-state.json"
            events.write_text(json.dumps({"items": [{
                "stable_item_key": "microsoft_external:email:obcn-42",
                "source_id": "obcn-42",
                "surface": "microsoft_external",
                "source_timestamp": "2026-08-10T09:00:00Z",
                "subject_or_location": "OBCN invoice INV-42",
                "raw_evidence_ref": "MICROSOFT_EXTERNAL.md",
                "thread_key": "obcn-42",
                "routing_flags": ["EXPENSE"],
                "reasons": ["supplier-cost evidence detected"],
            }]}), encoding="utf-8")
            expenses.write_text("# Expenses\n\n## Domains\n", encoding="utf-8")
            queue = root / "expense-enrichment-queue.json"
            old_events, old_expenses, old_monitored, old_queue = WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_LEDGER_PATH, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE
            try:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_LEDGER_PATH, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE = events, expenses, monitored, queue
                state, summary = WATCHER.default_state(), {}
                with patch.object(WATCHER, 'capture_sharepoint_candidate') as capture:
                    capture.return_value = BoundaryResult(
                        operation="capture", path="/Expenses/Expense ledger.xlsx",
                        accepted=True, verified=True,
                        canonical_ref="sharepoint:pending:obcn-42",
                    )
                    WATCHER.process_mirror_expense_events(state, summary)
                    WATCHER.process_mirror_expense_events(state, summary)  # replay must be idempotent
                self.assertEqual(summary["mirror_blocked"], 1)
                capture.assert_called_once()
                self.assertEqual(expenses.read_text(encoding="utf-8"), "# Expenses\n\n## Domains\n")
                self.assertFalse(queue.exists())
                item = json.loads(monitored.read_text(encoding="utf-8"))["items"][0]
                self.assertEqual(item["expense_outcome"], "blocked")
                self.assertEqual(item["canonical_ref"], "sharepoint:pending:obcn-42")
                self.assertEqual(item["ledger_state"], "pending")
                self.assertEqual(item["evidence_state"], "blocked")
            finally:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_LEDGER_PATH, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE = old_events, old_expenses, old_monitored, old_queue

    def test_failed_canonical_row_write_keeps_external_candidate_in_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events, expenses, monitored, queue = (root / "events.json", root / "expenses.md", root / "monitored.json", root / "queue.json")
            events.write_text(json.dumps({"items": [{
                "stable_item_key": "teams:expense:fail-1", "source_id": "fail-1", "surface": "teams_recent",
                "source_timestamp": "2026-08-10T10:00:00Z", "subject_or_location": "Expense evidence",
                "raw_evidence_ref": "TEAMS_RECENT.md", "routing_flags": ["EXPENSE"], "reasons": ["cost evidence"],
            }]}), encoding="utf-8")
            expenses.write_text("# Expenses\n(no insertion marker)\n", encoding="utf-8")
            old = WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_LEDGER_PATH, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE
            try:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_LEDGER_PATH, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE = events, expenses, monitored, queue
                with patch.object(WATCHER, 'capture_sharepoint_candidate') as capture:
                    capture.return_value = BoundaryResult(
                        operation="capture", path="/Expenses/Expense ledger.xlsx",
                        accepted=False, verified=False, blocker="capture unavailable",
                    )
                    WATCHER.process_mirror_expense_events(WATCHER.default_state(), {})
                capture.assert_called_once()
                self.assertFalse(queue.exists())
                self.assertEqual(expenses.read_text(encoding="utf-8"), "# Expenses\n(no insertion marker)\n")
            finally:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_LEDGER_PATH, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE = old

    def test_capture_without_canonical_ref_never_claims_sharepoint_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events, expenses, monitored, queue = (
                root / "events.json",
                root / "expenses.md",
                root / "monitored.json",
                root / "queue.json",
            )
            events.write_text(json.dumps({"items": [{
                "stable_item_key": "teams:expense:no-id",
                "source_id": "no-id",
                "surface": "teams_recent",
                "source_timestamp": "2026-08-10T10:00:00Z",
                "subject_or_location": "Expense evidence",
                "raw_evidence_ref": "TEAMS_RECENT.md",
                "routing_flags": ["EXPENSE"],
                "reasons": ["cost evidence"],
            }]}), encoding="utf-8")
            expenses.write_text("# Expenses\n(no insertion marker)\n", encoding="utf-8")
            old = WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_LEDGER_PATH, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE
            try:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_LEDGER_PATH, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE = events, expenses, monitored, queue
                with patch.object(WATCHER, "capture_sharepoint_candidate") as capture:
                    capture.return_value = BoundaryResult(
                        operation="capture", path="/Expenses/Expense ledger.xlsx",
                        accepted=True, verified=False,
                    )
                    WATCHER.process_mirror_expense_events(WATCHER.default_state(), {})
                item = json.loads(monitored.read_text(encoding="utf-8"))["items"][0]
                self.assertIsNone(item["canonical_ref"])
                self.assertIn("readback", item["blocker"])
                self.assertEqual(["TEAMS_RECENT.md"], item["evidence_refs"])
            finally:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_LEDGER_PATH, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE = old


class ExpenseReplayManifestTests(unittest.TestCase):
    def test_replay_finalization_preserves_append_and_enrichment_after_processing_began(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            replay = root / "replay.json"
            source_ref = "email:receipt:interleaving"
            appended_ref = "email:receipt:appended-during-processing"
            replay.write_text(json.dumps({
                "schema_version": 1,
                "items": [{
                    "source_surface": "email",
                    "source_ref": source_ref,
                    "facts": {"supplier": "Original"},
                }],
            }), encoding="utf-8")
            appended = False

            def capture_and_interleave(*, source_surface, source_ref, facts, boundary):
                nonlocal appended
                if not appended:
                    appended = True
                    replay.write_text(json.dumps({
                        "schema_version": 1,
                        "items": [
                            {
                                "source_surface": "email",
                                "source_ref": source_ref,
                                "facts": {"supplier": "Original"},
                            },
                            {
                                "source_surface": "email",
                                "source_ref": appended_ref,
                                "facts": {"supplier": "Appended during processing"},
                            },
                        ],
                    }), encoding="utf-8")
                return BoundaryResult(
                    operation="capture",
                    path="/Expenses/Expense ledger.xlsx",
                    accepted=True,
                    verified=True,
                    canonical_ref=f"/Expenses/Expense ledger.xlsx#{source_ref}",
                )

            with patch.object(WATCHER, "capture_candidate", side_effect=capture_and_interleave):
                states = WATCHER.process_expense_replay({}, replay_path=replay)

            self.assertEqual("success", states[0]["state"])
            saved_items = json.loads(replay.read_text(encoding="utf-8"))["items"]
            self.assertEqual(appended_ref, saved_items[0]["source_ref"])
            self.assertEqual("Appended during processing", saved_items[0]["facts"]["supplier"])

    def test_pending_conflict_is_retained_when_facts_change_during_processing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            replay = root / "replay.json"
            source_ref = "email:receipt:pending-conflict"
            replay.write_text(json.dumps({
                "schema_version": 1,
                "items": [{
                    "source_surface": "email",
                    "source_ref": source_ref,
                    "facts": {"supplier": "Before enrichment"},
                }],
            }), encoding="utf-8")
            def capture_then_enrich(*, source_surface, source_ref, facts, boundary):
                replay.write_text(json.dumps({
                    "schema_version": 1,
                    "items": [{
                        "source_surface": "email",
                        "source_ref": source_ref,
                        "facts": {
                            "supplier": "Enriched while write was pending",
                            "amount_pence": 1200,
                        },
                    }],
                }), encoding="utf-8")
                return BoundaryResult(
                    operation="capture",
                    path="/Expenses/Expense ledger.xlsx",
                    accepted=True,
                    verified=False,
                    blocker="SharePoint queue result/readback pending",
                )

            with patch.object(WATCHER, "capture_candidate", side_effect=capture_then_enrich):
                states = WATCHER.process_expense_replay({}, replay_path=replay)

            self.assertEqual("blocked", states[0]["state"])
            saved = json.loads(replay.read_text(encoding="utf-8"))["items"]
            self.assertEqual("Enriched while write was pending", saved[0]["facts"]["supplier"])
            self.assertEqual(1200, saved[0]["facts"]["amount_pence"])

    def test_malformed_manifest_written_during_processing_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            replay = root / "replay.json"
            replay.write_text(json.dumps({
                "schema_version": 1,
                "items": [{
                    "source_surface": "email",
                    "source_ref": "email:receipt:malformed-interleaving",
                    "facts": {"supplier": "Original"},
                }],
            }), encoding="utf-8")
            malformed = b'{"items": ['

            def capture_then_corrupt(*, source_surface, source_ref, facts, boundary):
                replay.write_bytes(malformed)
                return BoundaryResult(
                    operation="capture",
                    path="/Expenses/Expense ledger.xlsx",
                    accepted=True,
                    verified=True,
                    canonical_ref="/Expenses/Expense ledger.xlsx#malformed-interleaving",
                )

            with patch.object(WATCHER, "LOG_FILE", root / "watcher.log"), \
                 patch.object(WATCHER, "capture_candidate", side_effect=capture_then_corrupt):
                states = WATCHER.process_expense_replay({}, replay_path=replay)

            self.assertEqual("success", states[0]["state"])
            self.assertEqual(malformed, replay.read_bytes())

    def test_invalid_replay_json_is_blocked_without_rewriting_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            replay = root / "replay.json"
            original = b'{"items": ['
            replay.write_bytes(original)

            with patch.object(WATCHER, "LOG_FILE", root / "watcher.log"):
                states = WATCHER.process_expense_replay(
                    {},
                    replay_path=replay,
                )

            self.assertEqual(
                [{"state": "blocked", "blocker": "replay_manifest_malformed"}],
                states,
            )
            self.assertEqual(original, replay.read_bytes())

    def test_replay_item_with_malformed_facts_is_preserved_without_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            replay = root / "replay.json"
            payload = {
                "schema_version": 1,
                "items": [{
                    "source_surface": "email",
                    "source_ref": "email:receipt:malformed",
                    "facts": ["not", "an", "object"],
                }],
            }
            replay.write_text(json.dumps(payload), encoding="utf-8")

            with patch.object(WATCHER, "LOG_FILE", root / "watcher.log"):
                with patch.object(WATCHER, "capture_candidate") as capture:
                    states = WATCHER.process_expense_replay(
                        {},
                        replay_path=replay,
                    )

            self.assertEqual(
                [{
                    "state": "blocked",
                    "source_ref": "email:receipt:malformed",
                    "blocker": "replay_item_malformed",
                }],
                states,
            )
            self.assertEqual(payload, json.loads(replay.read_text(encoding="utf-8")))
            capture.assert_not_called()

    def test_receipt_replay_uses_boundary_and_never_writes_queue_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            replay = root / "replay.json"
            receipt = root / "receipt.pdf"
            receipt.write_bytes(b"fixture receipt")
            source_ref = "email:receipt:replay-idempotent"
            replay.write_text(json.dumps({
                "schema_version": 1,
                "items": [{
                    "source_surface": "email",
                    "source_ref": source_ref,
                    "facts": {
                        "receipt_path": str(receipt),
                        "receipt_mime_type": "application/pdf",
                    },
                }],
            }), encoding="utf-8")
            complete_capture = BoundaryResult(
                operation="capture",
                path="/Expenses/Expense ledger.xlsx",
                accepted=True,
                verified=True,
                canonical_ref="/Expenses/Expense ledger.xlsx#receipt-replay-idempotent",
            )

            class ReceiptTransport:
                store = object()

                def __init__(self) -> None:
                    self.calls = []

                def upload_receipt_verified(self, **kwargs):
                    self.calls.append(kwargs)
                    return BoundaryResult(
                        operation="upload_binary",
                        path=kwargs["path"],
                        accepted=True,
                        verified=True,
                        canonical_ref=kwargs["path"],
                    )

            transport = ReceiptTransport()
            boundary = _SeerFinanceBoundaryAdapter(transport)
            with (
                patch.object(WATCHER, "capture_candidate", return_value=complete_capture),
                patch.object(WATCHER, "resolve_boundary", return_value=boundary),
            ):
                delivered = WATCHER.process_expense_replay({}, replay_path=replay)
            self.assertEqual("success", delivered[0]["state"])
            self.assertEqual([], json.loads(replay.read_text(encoding="utf-8"))["items"])
            self.assertFalse((root / "sharepoint-queue.json").exists())
            self.assertEqual(source_ref, transport.calls[0]["source_ref"])
            self.assertEqual(receipt, transport.calls[0]["local_path"])


class SharePointCacheSafetyTests(unittest.TestCase):
    def test_generic_write_cannot_target_canonical_workbook(self) -> None:
        class UnexpectedBoundary:
            def write_verified(self, *args, **kwargs):
                raise AssertionError("generic canonical write must not reach transport")

        result = write_verified(
            "/Finance/Finance ledger.xlsx",
            "not-an-xlsx-workbook",
            operation="append",
            boundary=UnexpectedBoundary(),
        )
        self.assertFalse(result.accepted)
        self.assertFalse(result.verified)
        self.assertIn("write_workbook_verified", result.blocker or "")

    def test_workbook_boundary_forwards_all_binary_and_semantic_preconditions(self) -> None:
        class WorkbookTransport:
            def __init__(self) -> None:
                self.store = object()
                self.kwargs = None

            def write_workbook_verified(self, path, content_base64, **kwargs):
                self.kwargs = (path, content_base64, kwargs)
                return BoundaryResult(
                    operation="update_workbook",
                    path=path,
                    accepted=True,
                    verified=True,
                    canonical_ref=f"{path}#verified",
                )

        transport = WorkbookTransport()
        adapter = _SeerFinanceBoundaryAdapter.__new__(_SeerFinanceBoundaryAdapter)
        adapter.transport = transport
        result = adapter.write_workbook_verified(
            "/Finance/Finance ledger.xlsx",
            "UEsDB...",
            content_sha256="a" * 64,
            base_etag='"etag"',
            expected_source_sha256="b" * 64,
            semantic_sha256="c" * 64,
        )
        self.assertTrue(result.complete)
        self.assertEqual(
            (
                "/Finance/Finance ledger.xlsx",
                "UEsDB...",
                {
                    "content_sha256": "a" * 64,
                    "base_etag": '"etag"',
                    "expected_source_sha256": "b" * 64,
                    "semantic_sha256": "c" * 64,
                },
            ),
            transport.kwargs,
        )

    def test_missing_cache_never_becomes_an_empty_capture_authority(self) -> None:
        class EmptyStore:
            writes = 0

            def write(self, **kwargs):
                self.writes += 1
                raise AssertionError("missing cache must not be initialized by watcher")

        class MissingTransport:
            def __init__(self) -> None:
                self.store = EmptyStore()

            def read(self, path: str) -> str:
                raise SharePointBoundaryError(f"cache missing for {path}")

        adapter = _SeerFinanceBoundaryAdapter(MissingTransport())
        result = adapter.capture_candidate(
            source_surface="email",
            source_ref="email:missing-cache",
            facts={"supplier": "Acme"},
        )
        self.assertTrue(result.accepted)
        self.assertFalse(result.verified)
        self.assertIn("pending readback", result.blocker or "")
        self.assertEqual(0, adapter.store.store.writes)

    def test_changed_cache_version_blocks_stale_whole_document_write(self) -> None:
        class Store:
            writes = 0

            def write(self, **kwargs):
                self.writes += 1
                return "unexpected"

        class ChangingTransport:
            def __init__(self) -> None:
                self.store = Store()
                self.reads = iter(["version-one", "version-two"])

            def read(self, path: str) -> str:
                return next(self.reads)

        transport = ChangingTransport()
        store = _ReadbackRequiredStore(transport)
        self.assertEqual("version-one", store.read("/Finance/Finance ledger.xlsx"))
        with self.assertRaises(SharePointBoundaryError):
            store.write(path="/Finance/Finance ledger.xlsx", content="new document")
        self.assertEqual(0, transport.store.writes)

    def test_retired_queue_boundary_never_writes_queue_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "sharepoint-queue.json"
            boundary = QueueBoundary(queue)
            blocked = boundary.write_verified(
                "/Finance/Finance ledger.xlsx",
                "unsafe append",
            )
            self.assertFalse(blocked.accepted)
            self.assertFalse(queue.exists())


class SeerRepositoryIntegrationTests(unittest.TestCase):
    def _transport(self, *, kind: str = "expense"):
        from seer_finance.ledger.workbook_codec import WorkbookCodec

        if kind == "finance":
            initial = WorkbookCodec.encode_finance({
                "schema_version": 1,
                "transactions": [],
            })
        else:
            initial = WorkbookCodec.encode_expense({
                "schema_version": 1,
                "expenses": [],
                "events": [],
                "collisions": [],
                "evidence": [],
            })

        class WorkbookStore:
            def __init__(self) -> None:
                self.content = initial
                self.etag = '"initial-etag"'
                self.writes = 0
                self.snapshot_reads = 0
                self.change_before_write = False

            def read_workbook_snapshot(self, path: str) -> dict:
                self.snapshot_reads += 1
                content = self.content
                etag = self.etag
                if self.change_before_write and self.snapshot_reads > 1:
                    content = initial + b"changed"
                    etag = '"changed-etag"'
                return {
                    "path": path,
                    "content_bytes": content,
                    "content_sha256": hashlib.sha256(content).hexdigest(),
                    "etag": etag,
                    "version": "version-1",
                }

            def write_workbook(self, **kwargs):
                self.writes += 1
                self.content = base64.b64decode(kwargs["content_base64"])
                self.etag = '"updated-etag"'
                return f'{kwargs["path"]}#updated'

        class Transport:
            def __init__(self) -> None:
                self.store = WorkbookStore()

        return Transport()

    def test_adapter_runs_actual_seer_expense_repository_against_workbook_store(self) -> None:
        from seer_finance.ledger.workbook_codec import WorkbookCodec

        transport = self._transport()
        adapter = _SeerFinanceBoundaryAdapter(transport)
        result = adapter.capture_candidate(
            source_surface="email",
            source_ref="email:repository-integration",
            facts={
                "supplier": "Acme",
                "amount_pence": 1200,
                "currency": "GBP",
                "expense_date": "2026-08-10",
                "category": "software",
            },
        )
        self.assertTrue(result.complete)
        self.assertTrue(result.canonical_ref.startswith("/Expenses/Expense ledger.xlsx#"))
        self.assertEqual(1, transport.store.writes)
        state = WorkbookCodec.decode(transport.store.content, kind="expense")
        self.assertEqual("email:repository-integration", state["expenses"][0]["source_ref"])
        self.assertGreaterEqual(transport.store.snapshot_reads, 2)

    def test_adapter_runs_actual_seer_finance_writer_against_workbook_store(self) -> None:
        from seer_finance.ledger.workbook_codec import WorkbookCodec

        transport = self._transport(kind="finance")
        result = _SeerFinanceBoundaryAdapter(transport).update_validated_expense({
            "txn_id": "txn:repository-integration",
            "date": "2026-08-10",
            "direction": "expense",
            "amount_pence": 1200,
            "description": "Acme software",
            "counterparty": "Acme",
            "category": "software",
            "source_ref": "email:finance-repository-integration",
        })
        self.assertTrue(result.complete)
        self.assertEqual("sharepoint:txn:repository-integration", result.canonical_ref)
        state = WorkbookCodec.decode(transport.store.content, kind="finance")
        self.assertEqual(
            "email:finance-repository-integration",
            state["transactions"][0]["source_ref"],
        )
        self.assertGreaterEqual(transport.store.snapshot_reads, 2)

    def test_workbook_snapshot_change_blocks_actual_repository_write(self) -> None:
        transport = self._transport()
        transport.store.change_before_write = True
        result = _SeerFinanceBoundaryAdapter(transport).capture_candidate(
            source_surface="email",
            source_ref="email:stale-repository-integration",
            facts={"supplier": "Acme"},
        )
        self.assertTrue(result.accepted)
        self.assertFalse(result.verified)
        self.assertIn("pending readback", result.blocker or "")
        self.assertEqual(0, transport.store.writes)

    def test_repeated_capture_uses_real_store_proof_without_duplicate_queue(self) -> None:
        from seer_finance.ledger.sharepoint_contract import (
            EXPENSE_LEDGER_PATH,
            SharePointDocumentStore,
        )
        from seer_finance.ledger.workbook_codec import WorkbookCodec

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "cache"
            queue = root / "queue.json"
            results = root / "results.json"
            initial = WorkbookCodec.encode_expense({
                "schema_version": 1,
                "expenses": [],
                "events": [],
                "collisions": [],
                "evidence": [],
            })
            target = cache / "Expenses" / "Expense ledger.xlsx"
            target.parent.mkdir(parents=True)
            target.write_bytes(initial)
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            (cache / ".manifest.json").write_text(json.dumps({
                "cached": {
                    "Expenses/Expense ledger.xlsx": {
                        "sp_path": EXPENSE_LEDGER_PATH,
                        "etag": "etag-0",
                        "version": "v0",
                        "synced_at": now,
                        "content_sha256": hashlib.sha256(initial).hexdigest(),
                        "semantic_sha256": WorkbookCodec.semantic_hash(initial),
                    },
                },
            }), encoding="utf-8")
            store = SharePointDocumentStore(
                queue_path=queue,
                results_path=results,
                cache_root=cache,
            )
            adapter = _SeerFinanceBoundaryAdapter(type("Transport", (), {"store": store})())
            facts = {
                "supplier": "Acme",
                "amount_pence": 1200,
                "currency": "GBP",
                "expense_date": "2026-08-10",
                "category": "software",
            }

            first = adapter.capture_candidate(
                source_surface="email",
                source_ref="email:real-store-repeat",
                facts=facts,
            )
            self.assertTrue(first.accepted)
            self.assertFalse(first.verified)
            operation = json.loads(queue.read_text(encoding="utf-8"))[0]
            self.assertEqual("update_workbook", operation["operation"])
            self.assertEqual("etag-0", operation["base_etag"])
            self.assertEqual("v0", operation["base_version"])
            self.assertEqual(
                hashlib.sha256(initial).hexdigest(),
                operation["expected_source_sha256"],
            )

            second = adapter.capture_candidate(
                source_surface="email",
                source_ref="email:real-store-repeat",
                facts=facts,
            )
            self.assertTrue(second.accepted)
            self.assertFalse(second.verified)
            self.assertEqual(
                [operation["id"]],
                [item["id"] for item in json.loads(queue.read_text(encoding="utf-8"))],
            )

            desired = base64.b64decode(operation["content_base64"])
            target.write_bytes(desired)
            updated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            (cache / ".manifest.json").write_text(json.dumps({
                "cached": {
                    "Expenses/Expense ledger.xlsx": {
                        "sp_path": EXPENSE_LEDGER_PATH,
                        "etag": "etag-1",
                        "version": "v1",
                        "synced_at": updated,
                        "content_sha256": hashlib.sha256(desired).hexdigest(),
                        "semantic_sha256": WorkbookCodec.semantic_hash(desired),
                    },
                },
            }), encoding="utf-8")
            results.write_text(json.dumps([{
                "id": operation["id"],
                "path": EXPENSE_LEDGER_PATH,
                "success": True,
                "processed_at": updated,
                "resulting_etag": "etag-1",
                "resulting_version": "v1",
                "readback_sha256": hashlib.sha256(desired).hexdigest(),
                "readback_semantic_workbook_sha256": WorkbookCodec.semantic_hash(desired),
            }]), encoding="utf-8")
            queue.write_text("[]", encoding="utf-8")

            third = adapter.capture_candidate(
                source_surface="email",
                source_ref="email:real-store-repeat",
                facts=facts,
            )
            self.assertTrue(third.complete)
            self.assertTrue(third.canonical_ref.startswith(f"{EXPENSE_LEDGER_PATH}#"))
            decoded = WorkbookCodec.decode_expense(desired)
            self.assertEqual(
                ["email:real-store-repeat"],
                [item["source_ref"] for item in decoded["expenses"]],
            )
            self.assertEqual([], json.loads(queue.read_text(encoding="utf-8")))


class MirrorTimestampAndTelegramGuardTests(unittest.TestCase):
    def test_malformed_future_timestamp_is_retained_but_cannot_be_operational_time(self) -> None:
        observed, raw, status = WATCHER.normalise_mirror_timestamp(
            "+058577-08-15T00:40:00.000Z",
            now=WATCHER.datetime(2026, 8, 10, 16, 0, tzinfo=WATCHER.timezone.utc),
        )
        self.assertEqual("2026-08-10T16:00:00Z", observed)
        self.assertEqual("+058577-08-15T00:40:00.000Z", raw)
        self.assertEqual("invalid", status)

    def test_telegram_system_prose_is_not_queued_as_an_expense(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events, expenses, monitored, queue = (root / "events.json", root / "expenses.md", root / "monitored.json", root / "queue.json")
            events.write_text(json.dumps({"items": [{
                "stable_item_key": "telegram:30215", "source_id": "telegram:30215", "surface": "telegram_inbound",
                "source_timestamp": "+058577-08-15T00:40:00.000Z",
                "subject_or_location": "Are expense monitoring systems fully up and running?",
                "raw_evidence_ref": "telegram:30215", "routing_flags": ["EXPENSE"],
                "reasons": ["expense keyword"],
            }]}), encoding="utf-8")
            expenses.write_text("# Expenses\n\n## Domains\n", encoding="utf-8")
            old = WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_LEDGER_PATH, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE
            try:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_LEDGER_PATH, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE = events, expenses, monitored, queue
                state, summary = WATCHER.default_state(), {}
                WATCHER.process_mirror_expense_events(state, summary)
                self.assertFalse(queue.exists())
                item = json.loads(monitored.read_text(encoding="utf-8"))["items"][0]
                self.assertEqual("not_needed", item["expense_outcome"])
                self.assertEqual("invalid", item["source_timestamp_status"])
                self.assertEqual("+058577-08-15T00:40:00.000Z", item["raw_source_timestamp"])
            finally:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_LEDGER_PATH, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE = old


class RuntimeStatePruningTests(unittest.TestCase):
    def test_prunes_stale_runtime_keys_and_bounds_history(self) -> None:
        state = {
            "scanned_non_candidates": ["live", "stale"],
            "item_states": {
                "live": {
                    "route": "email",
                    "status": "classified",
                    "history": [{"stage": str(i)} for i in range(12)],
                },
                "stale": {"route": "email", "status": "not_needed", "history": [{"stage": "old"}]},
            },
        }
        WATCHER.prune_runtime_state(state, {"live"})
        self.assertEqual(state["scanned_non_candidates"], ["live"])
        self.assertEqual(set(state["item_states"]), {"live"})
        self.assertEqual(len(state["item_states"]["live"]["history"]), WATCHER.MAX_LIFECYCLE_HISTORY)


class MonitoredLedgerReconciliationTests(unittest.TestCase):
    def test_visible_non_material_email_cannot_leave_active_monitored_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            monitored = Path(tmp) / "monitored.json"
            entry = WATCHER.MailEntry(
                account="gmail",
                section="inbox",
                mailbox_path=Path("/tmp/GMAIL_INBOX.md"),
                subject="Quick hello",
                party="friend@example.com",
                date_str="Fri, 28 Aug 2026 09:00:00 +0000",
                message_id="low-signal-email",
                body_preview="Just checking in.",
            )
            monitored.write_text(json.dumps({
                "items": [{
                    "id": WATCHER.mail_key(entry),
                    "surface": "gmail_inbox",
                    "closure_state": "routed",
                    "management_relevance": "needs_management",
                }]
            }), encoding="utf-8")
            old_monitored = WATCHER.MONITORED_FILE
            try:
                WATCHER.MONITORED_FILE = monitored
                state, summary = WATCHER.default_state(), {}
                WATCHER.reconcile_monitored_items(state, [entry], [], summary)
                self.assertEqual(json.loads(monitored.read_text(encoding="utf-8"))["items"], [])
                self.assertEqual(state["item_states"][WATCHER.mail_key(entry)]["status"], "not_needed")
                self.assertEqual(summary["reconciled"], 1)
            finally:
                WATCHER.MONITORED_FILE = old_monitored

    def test_superseded_direct_inbound_is_removed_after_later_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            monitored = Path(tmp) / "monitored.json"
            now = WATCHER.datetime.now(WATCHER.timezone.utc).replace(microsecond=0)
            inbound = WATCHER.WhatsAppEntry(
                timestamp=(now - WATCHER.timedelta(hours=2)).isoformat(),
                contact="Lauren",
                text="Can you send the details?",
                raw_line="",
            )
            reply = WATCHER.WhatsAppEntry(
                timestamp=(now - WATCHER.timedelta(hours=1)).isoformat(),
                contact="Me",
                text="Sounds good.",
                raw_line="",
                direct_thread_contact="Lauren",
            )
            monitored.write_text(json.dumps({
                "items": [WATCHER.whatsapp_monitored_payload(
                    inbound, "routed", "Waiting for a reply", flags=["FOLLOW_UP"]
                )]
            }), encoding="utf-8")
            old_monitored = WATCHER.MONITORED_FILE
            try:
                WATCHER.MONITORED_FILE = monitored
                state, summary = WATCHER.default_state(), {}
                WATCHER.reconcile_monitored_items(state, [], [inbound, reply], summary)
                self.assertEqual(json.loads(monitored.read_text(encoding="utf-8"))["items"], [])
                self.assertEqual(state["item_states"][inbound.key]["detail"], "Superseded by newer direct-thread context")
            finally:
                WATCHER.MONITORED_FILE = old_monitored

    def test_outbound_acknowledgement_does_not_prune_blocked_direct_expense(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            monitored = Path(tmp) / "monitored.json"
            now = WATCHER.datetime.now(WATCHER.timezone.utc).replace(microsecond=0)
            expense = WATCHER.WhatsAppEntry(
                timestamp=(now - WATCHER.timedelta(hours=2)).isoformat(),
                contact="Supplier",
                text="I paid £42 for the client taxi receipt",
                raw_line="",
            )
            acknowledgement = WATCHER.WhatsAppEntry(
                timestamp=(now - WATCHER.timedelta(hours=1)).isoformat(),
                contact="Me",
                text="Thanks",
                raw_line="",
                direct_thread_contact="Supplier",
            )
            blocked = WATCHER.whatsapp_monitored_payload(
                expense,
                "blocked",
                "Captured in SharePoint; WhatsApp expense signal needs explicit "
                "business/payment/evidence review before finance posting",
                flags=["EXPENSE"],
            )
            monitored.write_text(json.dumps({"items": [blocked]}), encoding="utf-8")
            old_monitored = WATCHER.MONITORED_FILE
            try:
                WATCHER.MONITORED_FILE = monitored
                state, summary = WATCHER.default_state(), {}
                with (
                    patch.object(WATCHER, "capture_sharepoint_candidate") as capture,
                    patch.object(WATCHER, "run_reader") as reader,
                ):
                    WATCHER.reconcile_monitored_items(
                        state, [], [expense, acknowledgement], summary
                    )
                capture.assert_not_called()
                reader.assert_not_called()
                items = json.loads(monitored.read_text(encoding="utf-8"))["items"]
                self.assertEqual([item["id"] for item in items], [expense.key])
                self.assertEqual(items[0]["closure_state"], "blocked")
                self.assertNotIn(expense.key, state["item_states"])
                self.assertNotIn("reconciled", summary)
            finally:
                WATCHER.MONITORED_FILE = old_monitored

    def test_direct_thread_retains_only_newest_canonical_item_without_recapture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            monitored = Path(tmp) / "monitored.json"
            now = WATCHER.datetime.now(WATCHER.timezone.utc).replace(microsecond=0)
            older = WATCHER.WhatsAppEntry(
                timestamp=(now - WATCHER.timedelta(hours=2)).isoformat(),
                contact="Lauren",
                text="Can you send the details?",
                raw_line="",
            )
            newer = WATCHER.WhatsAppEntry(
                timestamp=(now - WATCHER.timedelta(hours=1)).isoformat(),
                contact="Lauren",
                text="Could you confirm what time?",
                raw_line="",
            )
            monitored.write_text(json.dumps({
                "items": [
                    WATCHER.whatsapp_monitored_payload(older, "routed", "Waiting", flags=["FOLLOW_UP"]),
                    WATCHER.whatsapp_monitored_payload(newer, "routed", "Waiting", flags=["FOLLOW_UP"]),
                ]
            }), encoding="utf-8")
            old_monitored = WATCHER.MONITORED_FILE
            try:
                WATCHER.MONITORED_FILE = monitored
                with (
                    patch.object(WATCHER, "capture_sharepoint_candidate") as capture,
                    patch.object(WATCHER, "run_reader") as reader,
                ):
                    WATCHER.reconcile_monitored_items(
                        WATCHER.default_state(), [], [newer, older], {}
                    )
                capture.assert_not_called()
                reader.assert_not_called()
                items = json.loads(monitored.read_text(encoding="utf-8"))["items"]
                self.assertEqual([item["id"] for item in items], [newer.key])
            finally:
                WATCHER.MONITORED_FILE = old_monitored


if __name__ == "__main__":
    unittest.main()
