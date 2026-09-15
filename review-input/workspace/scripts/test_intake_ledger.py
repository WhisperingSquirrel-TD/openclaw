#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import intake_ledger as ledger


class IntakeLedgerTests(unittest.TestCase):
    def event(self) -> dict:
        return {
            "surface": "linkedin_messages",
            "provider_event_id": "message-42",
            "provider_conversation_id": "thread-9",
            "source_timestamp": "2026-08-27T13:00:00Z",
            "observed_at": "2026-08-27T13:01:00Z",
            "evidence_refs": ["linkedin://thread-9/message-42"],
            "identity_state": "receipt_safe",
            "classification": "commercial_lead",
            "confidence": "high",
            "entity_state": "unmapped",
            "entity_refs": [],
            "route_set": ["alert", "crm", "sharepoint"],
        }

    def health(self) -> dict:
        return {
            "cadence": "PT15M",
            "last_successful_visible_update": "2026-08-27T13:00:00Z",
            "watermark": "message-42",
            "last_attempt": "2026-08-27T13:01:00Z",
            "captured_count": 1,
            "routed_count": 1,
            "verified_count": 0,
            "blocked_count": 1,
            "duplicate_count": 0,
            "oldest_blocker": "2026-08-27T13:01:00Z",
            "last_error": None,
            "runtime_duration_ms": 12,
            "coverage_state": "blocked",
        }

    def test_event_is_deduplicated_and_evidence_is_merged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, created = ledger.record_event(self.event(), root=root)
            enriched = self.event()
            enriched["evidence_refs"].append("mirror-events.json")
            second, created_again = ledger.record_event(enriched, root=root)
            self.assertTrue(created)
            self.assertFalse(created_again)
            self.assertEqual(first["event_id"], second["event_id"])
            self.assertEqual(second["evidence_refs"], ["linkedin://thread-9/message-42", "mirror-events.json"])
            self.assertEqual(len((root / ledger.EVENTS_FILE).read_text().splitlines()), 1)

    def test_identityless_event_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "provider_event_id or provider_conversation_id"):
            ledger.canonical_event_id(surface="teams_recent", provider_event_id=None, provider_conversation_id=None)

    def test_receipt_attempts_are_durable_and_health_has_all_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event, _ = ledger.record_event(self.event(), root=root)
            receipt = {
                "event_id": event["event_id"], "route": "crm", "state": "blocked", "owner": "crm-capture-handoff",
                "evidence_ref": "linkedin://thread-9/message-42", "destination_ref": None,
                "error_code": "entity_mapping_required", "next_review_at": "2026-08-27T14:00:00Z",
            }
            first, created = ledger.record_receipt(receipt, root=root)
            receipt["state"] = "verified"
            receipt["destination_ref"] = "crm:Fixture Co"
            receipt["error_code"] = None
            second, created_again = ledger.record_receipt(receipt, root=root)
            self.assertTrue(created)
            self.assertFalse(created_again)
            self.assertEqual(first["attempt"], 1)
            self.assertEqual(second["attempt"], 2)
            health = ledger.update_surface_health("linkedin_messages", self.health(), root=root)
            self.assertEqual(health["coverage_state"], "blocked")
            self.assertEqual(health["watermark"], "message-42")


if __name__ == "__main__":
    unittest.main()
