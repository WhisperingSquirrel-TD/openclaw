#!/usr/bin/env python3
"""Regression tests for the pure calendar/SharePoint origin adapters."""
from __future__ import annotations

import unittest

from operational_surface_adapters import (
    normalise_calendar_change,
    normalise_operational_surface_change,
    normalise_sharepoint_change,
)


class OperationalSurfaceAdapterTests(unittest.TestCase):
    def test_calendar_change_is_normalised_with_calendar_owned_route(self) -> None:
        change = {
            "provider_event_id": "graph-event-123",
            "provider_change_id": "graph-change-456",
            "source_timestamp": "2026-08-28T06:55:00Z",
            "observed_at": "2026-08-28T07:00:00Z",
            "evidence_ref": "fixture://calendar/graph-event-123/graph-change-456",
            "change_type": "updated",
            # Deliberately non-unique material must not drive identity.
            "subject": "Weekly review",
        }

        result = normalise_calendar_change(change)

        self.assertEqual(result["surface"], "calendar")
        self.assertEqual(result["provider_event_id"], "graph-event-123")
        self.assertEqual(result["provider_resource_id"], "graph-event-123")
        self.assertEqual(result["provider_change_id"], "graph-change-456")
        self.assertEqual(result["identity_state"], "receipt_safe")
        self.assertEqual(result["proposed_routes"], [{"route": "calendar", "owner": "calendar", "state": "proposed"}])
        self.assertFalse(result["adapter_metadata"]["external_writes"])

    def test_sharepoint_change_is_normalised_with_sharepoint_owned_route(self) -> None:
        change = {
            "provider_item_id": "drive-item-123",
            "change_id": "delta-456",
            "last_modified_at": "2026-08-28T06:55:00Z",
            "observed_at": "2026-08-28T07:00:00Z",
            "evidence_ref": "fixture://sharepoint/drive-item-123/delta-456",
            "change_kind": "deleted",
            "web_url": "https://example.test/sites/demo/doc.docx",
        }

        result = normalise_sharepoint_change(change)

        self.assertEqual(result["surface"], "sharepoint")
        self.assertEqual(result["provider_item_id"], "drive-item-123")
        self.assertEqual(result["provider_resource_id"], "drive-item-123")
        self.assertEqual(result["change_type"], "deleted")
        self.assertEqual(result["proposed_routes"], [{"route": "sharepoint", "owner": "sharepoint", "state": "proposed"}])

    def test_calendar_fails_closed_when_only_subject_identity_is_supplied(self) -> None:
        with self.assertRaisesRegex(ValueError, "provider_event_id is required"):
            normalise_calendar_change(
                {
                    "subject": "Weekly review",
                    "provider_change_id": "change-1",
                    "source_timestamp": "2026-08-28T06:55:00Z",
                    "observed_at": "2026-08-28T07:00:00Z",
                    "evidence_ref": "fixture://calendar/unknown",
                }
            )

    def test_sharepoint_fails_closed_when_only_path_identity_is_supplied(self) -> None:
        with self.assertRaisesRegex(ValueError, "provider_item_id is required"):
            normalise_sharepoint_change(
                {
                    "server_relative_url": "/Shared Documents/Weekly review.docx",
                    "provider_change_id": "change-1",
                    "source_timestamp": "2026-08-28T06:55:00Z",
                    "observed_at": "2026-08-28T07:00:00Z",
                    "evidence_ref": "fixture://sharepoint/unknown",
                }
            )

    def test_missing_change_identity_or_evidence_cannot_make_a_receipt(self) -> None:
        base = {
            "provider_event_id": "graph-event-123",
            "source_timestamp": "2026-08-28T06:55:00Z",
            "observed_at": "2026-08-28T07:00:00Z",
            "evidence_ref": "fixture://calendar/graph-event-123",
        }
        with self.assertRaisesRegex(ValueError, "provider_change_id is required"):
            normalise_calendar_change(base)
        with self.assertRaisesRegex(ValueError, "evidence_ref is required"):
            normalise_calendar_change({**base, "provider_change_id": "change-1", "evidence_ref": ""})

    def test_dispatch_is_bounded_to_the_two_supported_surfaces(self) -> None:
        with self.assertRaisesRegex(ValueError, "calendar or sharepoint"):
            normalise_operational_surface_change("crm", {})


if __name__ == "__main__":
    unittest.main()
