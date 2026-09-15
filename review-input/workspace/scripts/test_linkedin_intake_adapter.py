#!/usr/bin/env python3
"""Integration coverage for the internal-only LinkedIn intake safe slice."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import intake_ledger as ledger
from linkedin_intake_adapter import normalise_linkedin_fixture, record_linkedin_fixture


class LinkedInIntakeAdapterTests(unittest.TestCase):
    def fixture(self) -> dict[str, str]:
        # Synthetic unique provider IDs: never a live LinkedIn message.
        return {
            "provider_event_id": "synthetic-linkedin-commercial-20260827-9f1c2a",
            "provider_conversation_id": "synthetic-linkedin-thread-20260827-9f1c2a",
            "source_timestamp": "2026-08-27T15:56:00Z",
            "observed_at": "2026-08-27T15:57:00Z",
            "next_review_at": "2026-08-28T09:00:00Z",
            "sender_name": "Synthetic Prospect",
            "message": "We would like a consulting proposal for our project scope and budget.",
            "evidence_ref": "fixture://linkedin/synthetic-linkedin-commercial-20260827-9f1c2a",
        }

    def test_normalisation_is_receipt_safe_and_unmapped(self) -> None:
        event = normalise_linkedin_fixture(self.fixture())
        self.assertEqual(event["surface"], "linkedin_messages")
        self.assertEqual(event["identity_state"], "receipt_safe")
        self.assertEqual(event["classification"], "commercial_lead")
        self.assertEqual(event["entity_state"], "unmapped_review_required")
        self.assertEqual(event["entity_refs"], [])
        self.assertEqual(event["route_set"], ["alert", "crm", "sharepoint"])
        self.assertFalse(event["adapter_metadata"]["external_writes"])
        self.assertFalse(event["adapter_metadata"]["automatic_entity_creation"])

    def test_records_one_event_and_three_internal_review_receipts_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = record_linkedin_fixture(self.fixture(), root=root)
            event = result["event"]
            receipts = result["receipts"]

            self.assertTrue(result["event_created"])
            self.assertTrue(event["event_id"].startswith("evt-"))
            self.assertEqual(len(receipts), 3)
            self.assertEqual([receipt["route"] for receipt in receipts], ["alert", "crm", "sharepoint"])
            self.assertEqual([receipt["state"] for receipt in receipts], ["pending", "blocked", "blocked"])
            self.assertEqual(receipts[1]["error_code"], "entity_mapping_required")
            self.assertEqual(receipts[2]["error_code"], "entity_mapping_required")
            self.assertTrue(all(receipt["destination_ref"] is None for receipt in receipts))

            events = [json.loads(line) for line in (root / ledger.EVENTS_FILE).read_text().splitlines()]
            stored_receipts = [json.loads(line) for line in (root / ledger.RECEIPTS_FILE).read_text().splitlines()]
            self.assertEqual(len(events), 1)
            self.assertEqual(len(stored_receipts), 3)
            self.assertEqual({row["event_id"] for row in stored_receipts}, {event["event_id"]})

    def test_repeat_fixture_is_deduplicated_without_creating_new_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = record_linkedin_fixture(self.fixture(), root=root)
            second = record_linkedin_fixture(self.fixture(), root=root)
            self.assertTrue(first["event_created"])
            self.assertFalse(second["event_created"])
            self.assertEqual(len((root / ledger.EVENTS_FILE).read_text().splitlines()), 1)
            self.assertEqual(len((root / ledger.RECEIPTS_FILE).read_text().splitlines()), 3)
            self.assertEqual([row["attempt"] for row in second["receipts"]], [2, 2, 2])

    def test_identityless_fixture_fails_closed_before_any_ledger_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = self.fixture()
            fixture.pop("provider_event_id")
            fixture.pop("provider_conversation_id")
            with self.assertRaisesRegex(ValueError, "provider_event_id or provider_conversation_id"):
                record_linkedin_fixture(fixture, root=root)
            self.assertFalse((root / ledger.EVENTS_FILE).exists())
            self.assertFalse((root / ledger.RECEIPTS_FILE).exists())


if __name__ == "__main__":
    unittest.main()
