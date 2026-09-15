from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from sharepoint_boundary import BoundaryResult, FINANCE_LEDGER_PATH

MODULE_PATH = Path(__file__).with_name("enrichment_resolution.py")
SPEC = importlib.util.spec_from_file_location("expense_enrichment_resolution", MODULE_PATH)
assert SPEC and SPEC.loader
RESOLUTION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RESOLUTION
SPEC.loader.exec_module(RESOLUTION)


class FakeBoundary:
    def __init__(self, *, verified: bool) -> None:
        self.verified = verified
        self.paths: list[str] = []

    def update_validated_expense(self, candidate: dict[str, object]) -> BoundaryResult:
        self.paths.append(FINANCE_LEDGER_PATH)
        return BoundaryResult(
            operation="update_workbook",
            path=FINANCE_LEDGER_PATH,
            accepted=True,
            verified=self.verified,
            blocker=None if self.verified else "readback pending",
        )

    def read(self, path: str) -> str:
        return ""


class ExpenseDirectionBoundaryTests(unittest.TestCase):
    def test_explicit_income_is_preserved_without_creating_an_expense_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "expense-enrichment-queue.json"
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
            boundary = FakeBoundary(verified=True)

            result = RESOLUTION.resolve_ready_items(queue, boundary)

            self.assertEqual({"written": 0, "duplicates": 0, "waiting": 1, "blocked": 0}, result)
            self.assertFalse(boundary.paths)
            saved = json.loads(queue.read_text(encoding="utf-8"))
            self.assertEqual("accounting_only", saved["items"][0]["state"])

    def test_verified_readback_marks_finance_handoff_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "expense-enrichment-queue.json"
            queue.write_text(json.dumps({"items": [{
                "source_id": "microsoft:expense:1",
                "source_surface": "email",
                "state": "needs_enrichment",
                "enrichment": {
                    "payment_settlement": "confirmed",
                    "evidence_state": "retained",
                    "transaction": {
                        "date": "2026-08-01",
                        "direction": "expense",
                        "amount_pence": 4000,
                        "description": "subscription",
                        "counterparty": "Microsoft",
                        "category": "software",
                        "source_ref": "microsoft:expense:1",
                    },
                },
            }]}), encoding="utf-8")
            boundary = FakeBoundary(verified=True)

            result = RESOLUTION.resolve_ready_items(queue, boundary)

            self.assertEqual(1, result["written"])
            self.assertEqual([FINANCE_LEDGER_PATH], boundary.paths)
            item = json.loads(queue.read_text(encoding="utf-8"))["items"][0]
            self.assertEqual("ledger_written", item["state"])


if __name__ == "__main__":
    unittest.main()