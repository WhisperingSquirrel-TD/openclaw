from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from seer_finance.ledger.expense_finance_bridge import FinancePostOutcome
from seer_finance.ledger.expense_repository import ExpenseRepository, ExpenseStatus
from seer_finance.ledger.expense_review_control import list_holding_tray, post_ready_expense, review_expense


class ExpenseReviewControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'ledger.sqlite3'
        self.repo = ExpenseRepository(self.db)

    def tearDown(self) -> None:
        self.repo.close()
        self.tmp.cleanup()

    def _capture(self):
        return self.repo.capture(source_surface='email', source_ref='email:receipt:1', supplier='Acme')

    def test_holding_tray_lists_only_unresolved_expenses(self) -> None:
        item = self._capture()
        self.repo.transition(item.expense_id, ExpenseStatus.NOT_BUSINESS)
        unresolved = self.repo.capture(source_surface='email', source_ref='email:receipt:2')
        tray = list_holding_tray(self.db)
        self.assertEqual([unresolved.expense_id], [row['expense_id'] for row in tray])

    def test_confirm_requires_complete_evidence_then_makes_ledger_ready(self) -> None:
        item = self._capture()
        with self.assertRaisesRegex(ValueError, 'lacks'):
            review_expense(expense_id=item.expense_id, decision='confirm', database=self.db)
        approved = review_expense(expense_id=item.expense_id, decision='confirm', database=self.db, facts={
            'amount_pence': 1234, 'currency': 'GBP', 'expense_date': '2026-08-10',
            'category': 'software', 'evidence_ref': 'email://receipt/1',
            'evidence_state': 'retained', 'settlement_state': 'confirmed',
        })
        self.assertEqual('ledger_ready', approved['expense']['status'])

    def test_post_is_exactly_once_after_explicit_confirmation(self) -> None:
        item = self._capture()
        review_expense(expense_id=item.expense_id, decision='confirm', database=self.db, facts={
            'amount_pence': 1234, 'currency': 'GBP', 'expense_date': '2026-08-10',
            'category': 'software', 'evidence_ref': 'email://receipt/1',
            'evidence_state': 'retained', 'settlement_state': 'confirmed',
        })
        tx = {'txn_id': 'expense-email-receipt-1', 'date': '2026-08-10', 'direction': 'expense',
              'amount_pence': 1234, 'description': 'Acme software receipt', 'counterparty': 'Acme',
              'category': 'software', 'source_ref': 'email:receipt:1'}
        first = post_ready_expense(expense_id=item.expense_id, transaction=tx, database=self.db)
        second = post_ready_expense(expense_id=item.expense_id, transaction=tx, database=self.db)
        self.assertEqual(FinancePostOutcome.POSTED, first.outcome)
        self.assertEqual(FinancePostOutcome.ALREADY_POSTED, second.outcome)


if __name__ == '__main__':
    unittest.main()
