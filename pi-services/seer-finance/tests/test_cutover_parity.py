from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from seer_finance.ledger.compare_legacy_sqlite import figures
from seer_finance.ledger.expense_capture_adapter import capture_candidate
from seer_finance.ledger.expense_finance_bridge import ExpenseFinanceBridge
from seer_finance.ledger.expense_repository import ExpenseRepository, ExpenseStatus
from seer_finance.ledger.legacy_transactions_migration import migrate
from seer_finance.ledger.loader import load_transactions
from seer_finance.ledger.sqlite_finance_writer import SqliteFinanceWriter
from seer_finance.ledger.sqlite_loader import load_finance_transactions


class CutoverParityTests(unittest.TestCase):
    def test_historical_and_reviewed_sources_have_identical_json_and_sqlite_figures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history, combined, database = root / "history.json", root / "combined.json", root / "ledger.sqlite3"
            historical = [
                {"txn_id":"income-1","date":"2026-01-01","direction":"income","amount_pence":100000,"description":"Example sale","counterparty":"Example Customer","category":"sales","source_ref":"history:income:1"},
                {"txn_id":"expense-1","date":"2026-01-02","direction":"expense","amount_pence":20000,"description":"Example software","counterparty":"Example Supplier","category":"software","source_ref":"history:expense:1"},
                {"txn_id":"capital-1","date":"2026-01-03","direction":"expense","amount_pence":30000,"description":"Example equipment","counterparty":"Example Equipment","category":"equipment","source_ref":"history:capital:1"},
                {"txn_id":"nontrading-1","date":"2026-01-04","direction":"expense","amount_pence":40000,"description":"Example dividend","counterparty":"Example Owner","category":"dividend","source_ref":"history:nontrading:1"},
            ]
            history.write_text(json.dumps(historical))
            self.assertEqual(3, migrate(transactions_path=history, database=database)["ledger_written"])
            self.assertEqual(0, migrate(transactions_path=history, database=database)["ledger_written"])
            for source_ref, txn_id, supplier, amount, category in [
                ("email:example:1", "email-1", "Example Email Supplier", 1500, "software"),
                ("whatsapp:example:1", "whatsapp-1", "Example WhatsApp Supplier", 2500, "travel"),
            ]:
                captured = capture_candidate(source_surface=source_ref.split(":")[0], source_ref=source_ref, database=database,
                    replay_path=root / "replay.json", facts={"supplier":supplier,"amount_pence":amount,"currency":"GBP","expense_date":"2026-01-05","category":category,"evidence_ref":"fixture:"+source_ref,"evidence_state":"retained","settlement_state":"confirmed"})
                self.assertEqual(captured.expense_id, capture_candidate(source_surface=source_ref.split(":")[0], source_ref=source_ref, database=database, replay_path=root / "replay.json", facts={"supplier":supplier,"amount_pence":amount,"currency":"GBP","expense_date":"2026-01-05","category":category,"evidence_ref":"fixture:"+source_ref,"evidence_state":"retained","settlement_state":"confirmed"}).expense_id)
                repo = ExpenseRepository(database)
                try:
                    repo.transition(captured.expense_id, ExpenseStatus.CONFIRMED); repo.transition(captured.expense_id, ExpenseStatus.LEDGER_READY)
                    proposal={"txn_id":txn_id,"date":"2026-01-05","direction":"expense","amount_pence":amount,"description":"Example reviewed expense","counterparty":supplier,"category":category,"source_ref":source_ref}
                    bridge=ExpenseFinanceBridge(repo, SqliteFinanceWriter(database))
                    self.assertEqual("posted", bridge.post(captured.expense_id, proposal).outcome.value)
                    self.assertEqual("already_posted", bridge.post(captured.expense_id, proposal).outcome.value)
                finally: repo.close()
                historical.append(proposal)
            combined.write_text(json.dumps(historical))
            self.assertEqual(figures(load_transactions(combined)), figures(load_finance_transactions(database)))
