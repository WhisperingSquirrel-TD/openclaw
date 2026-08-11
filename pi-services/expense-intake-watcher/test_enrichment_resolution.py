from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("enrichment_resolution.py")
SPEC = importlib.util.spec_from_file_location("expense_enrichment_resolution", MODULE_PATH)
assert SPEC and SPEC.loader
RESOLUTION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RESOLUTION
SPEC.loader.exec_module(RESOLUTION)


class ExpenseDirectionBoundaryTests(unittest.TestCase):
    def test_explicit_income_is_preserved_without_creating_an_expense_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = root / "expense-enrichment-queue.json"
            database = root / "expense-ledger.sqlite3"
            queue.write_text(json.dumps({"items": [{
                "source_id": "tide:income:1",
                "source_surface": "tide_statement",
                "state": "needs_enrichment",
                "enrichment": {
                    "payment_settlement": "confirmed",
                    "evidence_state": "retained",
                    "transaction": {
                        "txn_id": "income-1",
                        "date": "2026-08-01",
                        "direction": "income",
                        "amount_pence": 4000,
                        "description": "PT income",
                        "counterparty": "Client",
                        "category": "sales",
                        "source_ref": "tide:income:1",
                    },
                },
            }]}), encoding="utf-8")

            result = RESOLUTION.resolve_ready_items(queue, database)

            self.assertEqual({"written": 0, "duplicates": 0, "waiting": 1, "blocked": 0}, result)
            self.assertFalse(database.exists())
            saved = json.loads(queue.read_text(encoding="utf-8"))
            item = saved["items"][0]
            self.assertEqual("accounting_only", item["state"])
            self.assertEqual("not_expense", item["ledger_state"])
            self.assertIn("excluded from expense workflow", item["blocker"])


if __name__ == "__main__":
    unittest.main()
