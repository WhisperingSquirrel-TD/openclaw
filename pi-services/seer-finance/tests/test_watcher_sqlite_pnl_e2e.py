from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from seer_finance.ledger.computation import summarise
from seer_finance.ledger.expense_capture_adapter import capture_candidate
from seer_finance.ledger.expense_finance_bridge import ExpenseFinanceBridge
from seer_finance.ledger.expense_repository import ExpenseRepository, ExpenseStatus
from seer_finance.ledger.sqlite_finance_writer import SqliteFinanceWriter
from seer_finance.ledger.sqlite_loader import load_finance_transactions

WATCHER_PATH = Path(__file__).resolve().parents[2] / "expense-intake-watcher" / "watcher.py"
sys.path.insert(0, str(WATCHER_PATH.parent))
SPEC = importlib.util.spec_from_file_location("portable_finance_watcher", WATCHER_PATH)
assert SPEC and SPEC.loader
WATCHER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = WATCHER
SPEC.loader.exec_module(WATCHER)


class WatcherToSqlitePnlE2ETests(unittest.TestCase):
    def test_superseded_whatsapp_reminder_does_not_remove_accounting_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database, replay, monitored = root / "ledger.sqlite3", root / "replay.json", root / "monitored.json"
            captured = capture_candidate(
                source_surface="whatsapp", source_ref="whatsapp:example:expense:1",
                database=database, replay_path=replay,
                facts={"supplier": "Example Rail Ltd", "amount_pence": 1250, "currency": "GBP",
                       "expense_date": "2026-08-28", "category": "travel",
                       "evidence_ref": "fixture:whatsapp:1", "evidence_state": "retained",
                       "settlement_state": "confirmed"},
            )
            inbound = WATCHER.WhatsAppEntry(timestamp="2026-08-28T10:00:00+00:00", contact="Example Contact",
                                             text="Can you send the expense details?", raw_line="")
            reply = WATCHER.WhatsAppEntry(timestamp="2026-08-28T10:05:00+00:00", contact="Me",
                                           text="Sent.", raw_line="", direct_thread_contact="Example Contact")
            monitored.write_text(json.dumps({"items": [WATCHER.whatsapp_monitored_payload(
                inbound, "routed", "Waiting", flags=["FOLLOW_UP"])]}))
            old_monitored = WATCHER.MONITORED_FILE
            try:
                WATCHER.MONITORED_FILE = monitored
                WATCHER.reconcile_monitored_items(WATCHER.default_state(), [], [inbound, reply], {})
            finally:
                WATCHER.MONITORED_FILE = old_monitored
            self.assertEqual([], json.loads(monitored.read_text())["items"])
            repository = ExpenseRepository(database)
            try:
                expense = repository.get(captured.expense_id)
                self.assertEqual(ExpenseStatus.NEEDS_REVIEW, expense.status)
                repository.transition(expense.expense_id, ExpenseStatus.CONFIRMED)
                repository.transition(expense.expense_id, ExpenseStatus.LEDGER_READY)
                proposal = {"txn_id": "example-whatsapp-expense-1", "date": "2026-08-28", "direction": "expense",
                            "amount_pence": 1250, "description": "Example rail travel", "counterparty": "Example Rail Ltd",
                            "category": "travel", "source_ref": "whatsapp:example:expense:1"}
                bridge = ExpenseFinanceBridge(repository, SqliteFinanceWriter(database))
                self.assertEqual("posted", bridge.post(expense.expense_id, proposal).outcome.value)
                self.assertEqual("already_posted", bridge.post(expense.expense_id, proposal).outcome.value)
            finally:
                repository.close()
            transactions = load_finance_transactions(database)
            self.assertEqual(1, len(transactions))
            self.assertEqual(1250, summarise(transactions).allowable_pence)
