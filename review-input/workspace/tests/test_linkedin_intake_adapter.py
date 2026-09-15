"""Synthetic receipt-safe LinkedIn vertical-slice tests."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "scripts"))

from linkedin_intake_adapter import record_linkedin_fixture  # noqa: E402


class LinkedInIntakeAdapterTests(unittest.TestCase):
    def _fixture(self, *, message: str, event_id: str) -> dict[str, str]:
        return {
            "provider_event_id": event_id,
            "provider_conversation_id": "conv-synthetic-001",
            "sender_name": "Avery Example",
            "message": message,
            "source_timestamp": "2026-08-28T05:45:00Z",
            "observed_at": "2026-08-28T05:46:00Z",
            "next_review_at": "2026-08-28T09:00:00Z",
            "evidence_ref": f"synthetic://linkedin/{event_id}",
        }

    def test_unique_mapped_commercial_event_creates_pending_internal_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = record_linkedin_fixture(
                self._fixture(message="Avery at Example Co would like a proposal for consulting.", event_id="msg-mapped-001"),
                root=Path(temporary),
                entity_candidates=[("Example Co", ["Example Co", "Avery Example"])],
            )
        self.assertTrue(result["event_created"])
        self.assertEqual(result["event"]["entity_state"], "mapped")
        self.assertEqual(result["event"]["entity_refs"], ["Example Co"])
        self.assertEqual(
            {(receipt["route"], receipt["state"], receipt["error_code"]) for receipt in result["receipts"]},
            {("alert", "pending", None), ("crm", "pending", None), ("sharepoint", "pending", None)},
        )

    def test_unique_unmapped_commercial_event_blocks_destination_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = record_linkedin_fixture(
                self._fixture(message="Avery would like a proposal for consulting.", event_id="msg-unmapped-001"),
                root=Path(temporary),
                entity_candidates=[("Different Co", ["Different Co", "Dana Different"])],
            )
        self.assertEqual(result["event"]["entity_state"], "unmapped_review_required")
        self.assertEqual(
            {(receipt["route"], receipt["state"], receipt["error_code"]) for receipt in result["receipts"]},
            {
                ("alert", "pending", None),
                ("crm", "blocked", "entity_mapping_required"),
                ("sharepoint", "blocked", "entity_mapping_required"),
            },
        )


if __name__ == "__main__":
    unittest.main()
