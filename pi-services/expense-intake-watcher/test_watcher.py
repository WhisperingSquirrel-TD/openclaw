#!/usr/bin/env python3
"""Focused regression tests for expense reference extraction/deduplication."""
from __future__ import annotations

import importlib.util
import sys
import json
import tempfile
import unittest
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
            old_events, old_expenses, old_monitored = WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_FILE, WATCHER.MONITORED_FILE
            try:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_FILE, WATCHER.MONITORED_FILE = events, expenses, monitored
                state, summary = WATCHER.default_state(), {}
                WATCHER.process_mirror_expense_events(state, summary)
                WATCHER.process_mirror_expense_events(state, summary)  # replay must be idempotent
                self.assertEqual(summary["mirror_blocked"], 1)
                self.assertIn("obcn-42", expenses.read_text(encoding="utf-8"))
                item = json.loads(monitored.read_text(encoding="utf-8"))["items"][0]
                self.assertEqual(item["expense_outcome"], "blocked")
                self.assertEqual(item["canonical_ref"], "seer-expenses.md#pending:obcn-42")
                self.assertEqual(item["ledger_state"], "pending")
                self.assertEqual(item["evidence_state"], "blocked")
            finally:
                WATCHER.MIRROR_EVENTS_FILE, WATCHER.EXPENSE_FILE, WATCHER.MONITORED_FILE = old_events, old_expenses, old_monitored


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


if __name__ == "__main__":
    unittest.main()
