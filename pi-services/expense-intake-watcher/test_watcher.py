#!/usr/bin/env python3
"""Focused regression tests for expense reference extraction/deduplication."""
from __future__ import annotations

import importlib.util
import sys
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

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
    def test_external_only_expense_event_gets_canonical_blocker_and_proof_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "mirror-events.json"
            expenses = root / "seer-expenses.md"
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
            old_events, old_expenses, old_monitored, old_queue = WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_FILE, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE
            try:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_FILE, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE = events, expenses, monitored, queue
                state, summary = WATCHER.default_state(), {}
                with patch.object(WATCHER, 'capture_sqlite_candidate') as capture:
                    capture.return_value.outcome = "captured"
                    capture.return_value.expense_id = "pending:obcn-42"
                    capture.return_value.blocker = None
                    WATCHER.process_mirror_expense_events(state, summary)
                    WATCHER.process_mirror_expense_events(state, summary)  # replay must be idempotent
                self.assertEqual(summary["mirror_blocked"], 1)
                capture.assert_called_once()
                self.assertEqual(expenses.read_text(encoding="utf-8"), "# Expenses\n\n## Domains\n")
                self.assertFalse(queue.exists())
                item = json.loads(monitored.read_text(encoding="utf-8"))["items"][0]
                self.assertEqual(item["expense_outcome"], "blocked")
                self.assertEqual(item["canonical_ref"], "sqlite:pending:obcn-42")
                self.assertEqual(item["ledger_state"], "pending")
                self.assertEqual(item["evidence_state"], "blocked")
            finally:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_FILE, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE = old_events, old_expenses, old_monitored, old_queue

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
            old = WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_FILE, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE
            try:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_FILE, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE = events, expenses, monitored, queue
                with patch.object(WATCHER, 'capture_sqlite_candidate') as capture:
                    WATCHER.process_mirror_expense_events(WATCHER.default_state(), {})
                capture.assert_called_once()
                self.assertFalse(queue.exists())
                self.assertEqual(expenses.read_text(encoding="utf-8"), "# Expenses\n(no insertion marker)\n")
            finally:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_FILE, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE = old


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
            old = WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_FILE, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE
            try:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_FILE, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE = events, expenses, monitored, queue
                state, summary = WATCHER.default_state(), {}
                WATCHER.process_mirror_expense_events(state, summary)
                self.assertFalse(queue.exists())
                item = json.loads(monitored.read_text(encoding="utf-8"))["items"][0]
                self.assertEqual("not_needed", item["expense_outcome"])
                self.assertEqual("invalid", item["source_timestamp_status"])
                self.assertEqual("+058577-08-15T00:40:00.000Z", item["raw_source_timestamp"])
            finally:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_FILE, WATCHER.MONITORED_FILE, WATCHER.ENRICHMENT_QUEUE_FILE = old


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
                    patch.object(WATCHER, "capture_sqlite_candidate") as capture,
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
