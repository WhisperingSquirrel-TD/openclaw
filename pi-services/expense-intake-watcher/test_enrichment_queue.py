from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from enrichment_queue import enqueue


class EnrichmentQueueTests(unittest.TestCase):
    def test_preserves_unknown_external_expense_once_with_required_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.json"
            kwargs = dict(source_id="obcn-42", source_surface="microsoft_external",
                          canonical_ref="seer-expenses.md#pending:obcn-42", blocker="body hidden")
            self.assertTrue(enqueue(queue, **kwargs))
            self.assertFalse(enqueue(queue, **kwargs))
            item = json.loads(queue.read_text(encoding="utf-8"))["items"][0]
            self.assertEqual(item["state"], "needs_enrichment")
            self.assertEqual(item["required_facts"], ["amount_pence", "category", "payment_settlement", "evidence_state"])

    def test_rejects_incomplete_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                enqueue(Path(tmp) / "queue.json", source_id="", source_surface="teams_recent",
                        canonical_ref="seer-expenses.md#pending:x", blocker="body hidden")


if __name__ == "__main__":
    unittest.main()
