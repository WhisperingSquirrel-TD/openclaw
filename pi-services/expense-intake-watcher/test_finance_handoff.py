from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finance_handoff import TransactionValidationError, append_validated_expense


class FinanceHandoffTests(unittest.TestCase):
    def candidate(self) -> dict:
        return {
            "txn_id": "expense-test-1",
            "date": "2026-08-10",
            "direction": "expense",
            "amount_pence": 42,
            "description": "Microsoft billing",
            "counterparty": "Microsoft",
            "category": "software",
            "source_ref": "microsoft:G175174660",
        }

    def test_appends_once_after_full_engine_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "transactions.json"
            ledger.write_text("[]\n", encoding="utf-8")
            self.assertTrue(append_validated_expense(ledger, self.candidate()))
            self.assertFalse(append_validated_expense(ledger, self.candidate()))
            self.assertEqual(len(json.loads(ledger.read_text(encoding="utf-8"))), 1)

    def test_refuses_incomplete_financial_data_without_mutating_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "transactions.json"
            ledger.write_text("[]\n", encoding="utf-8")
            bad = self.candidate()
            bad.pop("category")
            with self.assertRaises(TransactionValidationError):
                append_validated_expense(ledger, bad)
            self.assertEqual(json.loads(ledger.read_text(encoding="utf-8")), [])


if __name__ == "__main__":
    unittest.main()
