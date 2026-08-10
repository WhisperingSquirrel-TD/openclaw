from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from enrichment_resolution import resolve_ready_items


class EnrichmentResolutionTests(unittest.TestCase):
    def _transaction(self) -> dict:
        return {
            "txn_id": "expense-obcn-42",
            "date": "2026-08-10",
            "direction": "expense",
            "amount_pence": 4200,
            "description": "OBCN breakfast",
            "counterparty": "OBCN",
            "category": "marketing",
            "source_ref": "obcn-42",
        }

    def _queue(self, path: Path, enrichment: dict | None) -> None:
        item = {"source_id": "obcn-42", "state": "needs_enrichment"}
        if enrichment is not None:
            item["enrichment"] = enrichment
        path.write_text(json.dumps({"schema_version": 1, "items": [item]}), encoding="utf-8")

    def test_only_confirmed_retained_evidence_writes_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); queue = root / "queue.json"; ledger = root / "ledger.json"
            ledger.write_text("[]", encoding="utf-8")
            self._queue(queue, {"payment_settlement": "confirmed", "evidence_state": "retained", "transaction": self._transaction()})
            self.assertEqual(resolve_ready_items(queue, ledger), {"written": 1, "duplicates": 0, "waiting": 0, "blocked": 0})
            self.assertEqual(json.loads(queue.read_text())["items"][0]["state"], "ledger_written")
            self.assertEqual(len(json.loads(ledger.read_text())), 1)

    def test_unenriched_candidate_cannot_touch_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); queue = root / "queue.json"; ledger = root / "ledger.json"
            ledger.write_text("[]", encoding="utf-8")
            self._queue(queue, None)
            self.assertEqual(resolve_ready_items(queue, ledger)["waiting"], 1)
            self.assertEqual(json.loads(ledger.read_text()), [])

    def test_mismatched_source_reference_blocks_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); queue = root / "queue.json"; ledger = root / "ledger.json"
            ledger.write_text("[]", encoding="utf-8")
            tx = self._transaction(); tx["source_ref"] = "wrong"
            self._queue(queue, {"payment_settlement": "confirmed", "evidence_state": "retained", "transaction": tx})
            self.assertEqual(resolve_ready_items(queue, ledger)["blocked"], 1)
            self.assertEqual(json.loads(ledger.read_text()), [])


if __name__ == "__main__":
    unittest.main()
