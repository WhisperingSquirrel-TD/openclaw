from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from seer_finance.ledger.sharepoint_contract import document_content
from seer_finance.ledger.workbook_codec import encode_finance_workbook, WorkbookCodec
from seer_finance.ledger.workbook_migration import merge_ledger_sources, migrate_sources


class WorkbookMigrationTests(unittest.TestCase):
    def test_latest_source_wins_and_historical_fields_are_retained(self) -> None:
        latest = {
            "schema_version": 1,
            "reviewed_by": "operator",
            "transactions": [{
                "txn_id": "txn-1",
                "amount_pence": 100,
                "description": "latest",
            }],
        }
        historical = {
            "schema_version": 1,
            "transactions": [{
                "txn_id": "txn-1",
                "amount_pence": 99,
                "counterparty": "Acme",
            }, {
                "txn_id": "txn-old",
                "amount_pence": 1,
            }],
        }
        merged = merge_ledger_sources([latest, historical], kind="finance")
        self.assertEqual("latest", merged["transactions"][0]["description"])
        self.assertEqual("Acme", merged["transactions"][0]["counterparty"])
        self.assertEqual(2, len(merged["transactions"]))
        self.assertEqual("operator", merged["reviewed_by"])

    def test_cli_migration_writes_local_workbook_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            markdown = root / "finance.md"
            markdown.write_text(document_content("Finance ledger", {
                "schema_version": 1,
                "transactions": [],
            }), encoding="utf-8")
            output = root / "Finance" / "Finance ledger.xlsx"
            report = migrate_sources(
                kind="finance", markdown=markdown, output=output, apply=True
            )
            self.assertTrue(output.exists())
            self.assertTrue(report["applied"])
            self.assertEqual([], WorkbookCodec.decode_finance(output.read_bytes())["transactions"])


if __name__ == "__main__":
    unittest.main()
