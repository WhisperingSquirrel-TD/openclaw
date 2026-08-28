from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from seer_finance.ledger.computation import summarise
from seer_finance.ledger.expense_capture_adapter import capture_candidate
from seer_finance.ledger.expense_finance_bridge import ExpenseFinanceBridge
from seer_finance.ledger.expense_repository import ExpenseRepository, ExpenseStatus
from seer_finance.ledger.sqlite_finance_writer import SqliteFinanceWriter
from seer_finance.ledger.sqlite_loader import load_finance_transactions


class SqlitePnlBridgeTests(unittest.TestCase):
    def test_reviewed_expense_reaches_pnl_exactly_once(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "finance.sqlite3"
            replay = Path(directory) / "replay.json"
            captured = capture_candidate(
                source_surface="email",
                source_ref="email:example-receipt:1",
                database=database,
                replay_path=replay,
                facts={"supplier": "Example Software Ltd", "amount_pence": 2499,
                       "currency": "GBP", "expense_date": "2026-08-28",
                       "category": "software", "evidence_ref": "fixture:email:1",
                       "evidence_state": "retained", "settlement_state": "confirmed"},
            )
            repository = ExpenseRepository(database)
            try:
                expense = repository.get(captured.expense_id)
                self.assertEqual(ExpenseStatus.NEEDS_REVIEW, expense.status)
                repository.transition(expense.expense_id, ExpenseStatus.CONFIRMED)
                repository.transition(expense.expense_id, ExpenseStatus.LEDGER_READY)
                bridge = ExpenseFinanceBridge(repository, SqliteFinanceWriter(database))
                proposal = {"txn_id": "example-expense-001", "date": "2026-08-28",
                            "direction": "expense", "amount_pence": 2499,
                            "description": "Example subscription", "counterparty": "Example Software Ltd",
                            "category": "software", "source_ref": "email:example-receipt:1"}
                self.assertEqual("posted", bridge.post(expense.expense_id, proposal).outcome.value)
                self.assertEqual("already_posted", bridge.post(expense.expense_id, proposal).outcome.value)
            finally:
                repository.close()
            transactions = load_finance_transactions(database)
            self.assertEqual(1, len(transactions))
            self.assertEqual(2499, summarise(transactions).allowable_pence)
