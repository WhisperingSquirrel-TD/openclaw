"""Focused non-live tests for the explicit expense-to-finance adapter."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from seer_finance.ledger.expense_finance_bridge import (
    ExpenseFinanceBridge,
    FinancePostOutcome,
    FinanceReferenceConflict,
)
from seer_finance.ledger.expense_repository import ExpenseRepository, ExpenseStatus
from seer_finance.ledger.schema import Transaction


class FakeWriter:
    def __init__(self, result: str = "finance:txn-1", error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.transactions: list[Transaction] = []

    def validate_and_write(self, transaction: Transaction) -> str:
        self.transactions.append(transaction)
        if self.error is not None:
            raise self.error
        return self.result


class ExpenseFinanceBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = ExpenseRepository(Path(self.tempdir.name) / "expenses.sqlite3")

    def tearDown(self) -> None:
        self.repo.close()
        self.tempdir.cleanup()

    def _ready_expense(self):
        expense = self.repo.capture(
            source_surface="email", source_ref="email:receipt:1", supplier="Acme Ltd",
            amount_pence=1234, currency="GBP", expense_date="2026-08-10",
            category="software", evidence_ref="email://receipt/1", evidence_state="retained",
            settlement_state="settled",
        )
        self.repo.transition(expense.expense_id, ExpenseStatus.CONFIRMED)
        return self.repo.transition(expense.expense_id, ExpenseStatus.LEDGER_READY)

    @staticmethod
    def _proposal() -> dict[str, object]:
        return {
            "txn_id": "expense-email-receipt-1", "date": "2026-08-10", "direction": "expense",
            "amount_pence": 1234, "description": "Acme software receipt", "counterparty": "Acme Ltd",
            "category": "software", "source_ref": "email:receipt:1",
        }

    def test_refuses_non_ready_and_incomplete_expenses_without_writer_call(self) -> None:
        non_ready = self.repo.capture(source_surface="email", source_ref="email:unreviewed")
        writer = FakeWriter()
        bridge = ExpenseFinanceBridge(self.repo, writer)

        refused = bridge.post(non_ready.expense_id, self._proposal())
        self.assertEqual(FinancePostOutcome.REFUSED, refused.outcome)
        self.assertEqual("expense_not_ledger_ready", refused.error_code)
        self.assertEqual(ExpenseStatus.NEEDS_REVIEW, self.repo.get(non_ready.expense_id).status)

        ready = self._ready_expense()
        incomplete = bridge.post(ready.expense_id, {"txn_id": "only-id"})
        self.assertEqual(FinancePostOutcome.REFUSED, incomplete.outcome)
        self.assertEqual("transaction_schema_incomplete", incomplete.error_code)
        self.assertEqual(ExpenseStatus.LEDGER_READY, self.repo.get(ready.expense_id).status)
        self.assertEqual([], writer.transactions)

    def test_refuses_capture_collision_without_losing_evidence(self) -> None:
        ready = self._ready_expense()
        self.repo.capture(source_surface="email", source_ref="email:receipt:1", supplier="Other Ltd")
        writer = FakeWriter()

        result = ExpenseFinanceBridge(self.repo, writer).post(ready.expense_id, self._proposal())

        self.assertEqual(FinancePostOutcome.BLOCKED, result.outcome)
        self.assertEqual("capture_collision_unresolved", result.error_code)
        self.assertEqual(ExpenseStatus.LEDGER_READY, self.repo.get(ready.expense_id).status)
        self.assertEqual("Acme Ltd", self.repo.get(ready.expense_id).supplier)
        self.assertEqual(1, len(self.repo.capture_collisions(ready.expense_id)))
        self.assertEqual([], writer.transactions)

    def test_success_is_exactly_once_and_retry_does_not_write_again(self) -> None:
        ready = self._ready_expense()
        writer = FakeWriter("existing-finance-ref:123")
        bridge = ExpenseFinanceBridge(self.repo, writer)

        posted = bridge.post(ready.expense_id, self._proposal())
        retry = bridge.post(ready.expense_id, self._proposal())

        self.assertEqual(FinancePostOutcome.POSTED, posted.outcome)
        self.assertEqual("existing-finance-ref:123", posted.finance_ledger_ref)
        self.assertEqual(FinancePostOutcome.ALREADY_POSTED, retry.outcome)
        self.assertEqual("existing-finance-ref:123", retry.finance_ledger_ref)
        self.assertEqual(1, len(writer.transactions))
        stored = self.repo.get(ready.expense_id)
        self.assertEqual(ExpenseStatus.LEDGER_WRITTEN, stored.status)
        self.assertEqual("existing-finance-ref:123", stored.finance_ledger_ref)

    def test_writer_reference_rejection_preserves_ready_status_and_no_reference(self) -> None:
        ready = self._ready_expense()
        writer = FakeWriter(error=FinanceReferenceConflict())

        result = ExpenseFinanceBridge(self.repo, writer).post(ready.expense_id, self._proposal())

        self.assertEqual(FinancePostOutcome.BLOCKED, result.outcome)
        self.assertEqual("finance_reference_conflict", result.error_code)
        stored = self.repo.get(ready.expense_id)
        self.assertEqual(ExpenseStatus.LEDGER_READY, stored.status)
        self.assertIsNone(stored.finance_ledger_ref)
        self.assertEqual(1, len(writer.transactions))


if __name__ == "__main__":
    unittest.main()
