#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).with_name("inbound-monitoring.py")
SPEC = importlib.util.spec_from_file_location("inbound_monitoring", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SharePointOriginWatcherTests(unittest.TestCase):
    def test_classifies_entity_current_files(self) -> None:
        result = MODULE.classify_sharepoint_path("Accounts/Croyde Medical/Croyde Medical - Current.md")
        self.assertEqual(result["file_class"], "entity_current")
        self.assertEqual(result["entity_kind"], "account")
        self.assertEqual(result["entity_name"], "Croyde Medical")

    def test_classifies_dated_entity_artifacts(self) -> None:
        result = MODULE.classify_sharepoint_path("Opportunities/Markets Recon/2026-06-23 - Communication Update - Proposal Sent.md")
        self.assertEqual(result["file_class"], "dated_artifact")
        self.assertEqual(result["entity_kind"], "opportunity")
        self.assertEqual(result["entity_name"], "Markets Recon")

    def test_classifies_meeting_copilot_landing_files(self) -> None:
        result = MODULE.classify_sharepoint_path("Meeting Agent Outputs/2026-06-27 - Meeting Summary - Croyde Service Workshop.md")
        self.assertEqual(result["file_class"], "meeting_copilot_landing")
        self.assertIsNone(result["entity_kind"])

    def test_manifest_candidate_detects_new_and_unchanged(self) -> None:
        meta = {"sp_modified": "2026-06-27T09:00:00Z", "size": 123, "local_path": "sharepoint-cache/Accounts/Croyde Medical/Croyde Medical - Current.md"}
        new_candidate = MODULE.candidate_from_manifest_entry("Accounts/Croyde Medical/Croyde Medical - Current.md", meta, {})
        self.assertEqual(new_candidate.change_state, "new")
        prior = {"Accounts/Croyde Medical/Croyde Medical - Current.md": {"last_seen_modified": "2026-06-27T09:00:00Z", "last_seen_size": 123}}
        unchanged_candidate = MODULE.candidate_from_manifest_entry("Accounts/Croyde Medical/Croyde Medical - Current.md", meta, prior)
        self.assertEqual(unchanged_candidate.change_state, "unchanged")

    def test_extract_current_summary_fields(self) -> None:
        sample = """# Example - Current
**Last touch:** 2026-06-27

## Current position
- Warm account.
- Decision due.

## Recommended next step
- Send a precise follow-up on Monday.

## Other
Ignore.
"""
        fields = MODULE.extract_current_summary_fields(sample)
        self.assertEqual(fields["last_touch"], "2026-06-27")
        self.assertIn("Send a precise follow-up", fields["next_step"])
        self.assertIn("Warm account", fields["current_position"])

    def test_parse_meeting_copilot_filename(self) -> None:
        parsed = MODULE.parse_meeting_copilot_filename("Meeting Agent Outputs/2026-06-27 - Meeting Summary - Croyde Service Workshop.md")
        self.assertTrue(parsed["matched"])
        self.assertEqual(parsed["date"], "2026-06-27")
        self.assertEqual(parsed["kind"], "Meeting Summary")
        self.assertEqual(parsed["title"], "Croyde Service Workshop")

    def test_normalise_current_header_content_updates_only_known_sections(self) -> None:
        content = """# Example - Current
**Last touch:** 2026-06-01

## Current position
- Keep this.

## Recommended next step
- Old next step.

## Notes
- Preserve this.
"""
        row = {"last_touch": "2026-06-27", "next_step": "New concrete next step."}
        proposal = {"current_next_step": "Old next step."}
        updated, changes, blockers = MODULE.normalise_current_header_content(content, row, proposal)
        self.assertEqual(blockers, [])
        self.assertIn("**Last touch:** 2026-06-27", updated)
        self.assertIn("- New concrete next step.", updated)
        self.assertIn("## Notes\n- Preserve this.", updated)
        self.assertEqual(changes, ["last_touch", "recommended_next_step"])

    def test_normalise_current_header_content_blocks_missing_sections(self) -> None:
        updated, changes, blockers = MODULE.normalise_current_header_content("# Example\n", {"last_touch": "2026-06-27", "next_step": "Next"}, {"current_next_step": "Old"})
        self.assertEqual(changes, [])
        self.assertIn("missing Last touch header line", blockers)
        self.assertIn("missing Recommended next step section", blockers)
        self.assertEqual(updated, "# Example\n")

    def test_add_missing_current_sections(self) -> None:
        updated, changes, blockers = MODULE.add_missing_current_sections("# Example\n\n## Current position\n- Keep.\n", {"last_touch": "2026-06-27", "next_step": "Next"})
        self.assertEqual(blockers, [])
        self.assertIn("**Last touch:** 2026-06-27", updated)
        self.assertIn("## Recommended next step", updated)
        self.assertEqual(changes, ["add_last_touch", "add_recommended_next_step"])

    def test_queue_contains_equivalent(self) -> None:
        queue = [{"path": "/Accounts/A/A - Current.md", "source": "source", "changes": ["b", "a"]}]
        self.assertTrue(MODULE.queue_contains_equivalent(queue, "Accounts/A/A - Current.md", "source", ["a", "b"]))
        self.assertFalse(MODULE.queue_contains_equivalent(queue, "Accounts/A/A - Current.md", "other", ["a", "b"]))

    def test_normalization_history_key_is_order_insensitive(self) -> None:
        a = MODULE.normalization_history_key("Accounts/A/A - Current.md", "source", ["b", "a"])
        b = MODULE.normalization_history_key("Accounts/A/A - Current.md", "source", ["a", "b"])
        self.assertEqual(a, b)

    def test_manifest_freshness_status(self) -> None:
        fresh = MODULE.manifest_freshness_status({"synced_at": MODULE.now_utc().isoformat()})
        self.assertEqual(fresh["status"], "fresh")
        missing = MODULE.manifest_freshness_status({})
        self.assertEqual(missing["status"], "coverage_incomplete")

    def test_meeting_copilot_landing_blocks_for_entity_identification(self) -> None:
        candidate = MODULE.SharePointFileCandidate(
            path="Meeting Agent Outputs/2026-06-27 - Meeting Summary - Unknown.md",
            file_class="meeting_copilot_landing",
            entity_kind=None,
            entity_name=None,
            modified="2026-06-27T09:00:00Z",
            size=456,
            local_path="sharepoint-cache/Meeting Agent Outputs/2026-06-27 - Meeting Summary - Unknown.md",
            change_state="new",
            reason="not present",
        )
        items = MODULE.meeting_copilot_routing_items([candidate])
        self.assertEqual(items[0]["outcome"], "blocked")
        self.assertIn("entity identification", items[0]["action"])

    def test_report_groups_dirty_entities_and_landing_items(self) -> None:
        candidates = [
            MODULE.SharePointFileCandidate(
                path="Accounts/Croyde Medical/Croyde Medical - Current.md",
                file_class="entity_current",
                entity_kind="account",
                entity_name="Croyde Medical",
                modified="2026-06-27T09:00:00Z",
                size=123,
                local_path="sharepoint-cache/Accounts/Croyde Medical/Croyde Medical - Current.md",
                change_state="modified",
                reason="metadata changed",
            ),
            MODULE.SharePointFileCandidate(
                path="Meeting Agent Outputs/2026-06-27 - Meeting Summary - Unknown.md",
                file_class="meeting_copilot_landing",
                entity_kind=None,
                entity_name=None,
                modified="2026-06-27T09:00:00Z",
                size=456,
                local_path="sharepoint-cache/Meeting Agent Outputs/2026-06-27 - Meeting Summary - Unknown.md",
                change_state="new",
                reason="not present",
            ),
        ]
        entities = {
            "account:Croyde Medical": {
                "entity_kind": "account",
                "entity_name": "Croyde Medical",
                "dirty": True,
                "dirty_reasons": ["modified:entity_current:Accounts/Croyde Medical/Croyde Medical - Current.md"],
                "changed_files": ["Accounts/Croyde Medical/Croyde Medical - Current.md"],
            }
        }
        report = MODULE.render_sharepoint_origin_report("2026-06-27T09:00:00Z", {"synced_at": "2026-06-27T08:50:00Z"}, candidates, candidates, entities, [candidates[1]], True)
        self.assertIn("account:Croyde Medical", report)
        self.assertIn("Meeting Copilot landing items", report)
        self.assertIn("Dry-run only", report)


class InboundMonitoringSurfaceCoverageTests(unittest.TestCase):
    def test_first_class_surfaces_have_runtime_specs(self) -> None:
        missing = [
            surface_key
            for surface_key in MODULE.FIRST_CLASS_INTAKE_SURFACES
            if surface_key not in MODULE.SURFACE_SPECS
        ]
        self.assertEqual(missing, [])

    def test_first_class_surfaces_have_existing_source_files(self) -> None:
        missing_files = [
            surface_key
            for surface_key in MODULE.FIRST_CLASS_INTAKE_SURFACES
            if not MODULE.SURFACE_SPECS[surface_key]["source_path"].exists()
        ]
        self.assertEqual(missing_files, [])

    def test_teams_surface_is_first_class_chat_surface(self) -> None:
        self.assertIn("teams_recent", MODULE.FIRST_CLASS_INTAKE_SURFACES)
        self.assertEqual(MODULE.SURFACE_SPECS["teams_recent"]["source_path"], MODULE.TEAMS_RECENT_PATH)
        self.assertEqual(MODULE.SURFACE_SPECS["teams_recent"]["kind"], "chat")

    def test_teams_timestamp_extraction_reads_poller_feed_lines(self) -> None:
        sample = """# TEAMS_RECENT.md
_Last updated: 2026-06-28T13:55:00Z_

## Recent Teams activity
- [2026-06-28 13:54 UTC] (chat) Example — Person: Message
"""
        ts = MODULE._extract_latest_visible_timestamp("teams_recent", sample)
        self.assertIsNotNone(ts)
        self.assertEqual(ts.strftime("%Y-%m-%d %H:%M"), "2026-06-28 13:54")

    def test_fresh_feed_with_no_item_timestamp_is_not_new_activity(self) -> None:
        report = MODULE._generic_continuity_report(
            surface_key="teams_recent",
            source_path=MODULE.TEAMS_RECENT_PATH,
            title="Teams Continuity Report",
            threshold_hours=2,
            latest_visible_ts=None,
        )
        if "OK — Teams poll completed" in MODULE.TEAMS_RECENT_PATH.read_text(errors="ignore"):
            self.assertIn("Result shape: no_new_visible_activity", report)

    def test_feed_reported_coverage_incomplete_fails_closed_even_when_fresh(self) -> None:
        report = MODULE._generic_continuity_report(
            surface_key="teams_recent",
            source_path=MODULE.TEAMS_RECENT_PATH,
            title="Teams Continuity Report",
            threshold_hours=2,
            latest_visible_ts=None,
        )
        if "Coverage incomplete:" in MODULE.TEAMS_RECENT_PATH.read_text(errors="ignore"):
            self.assertIn("Coverage state: incomplete", report)

    def test_teams_item_classification_uses_standard_followup_flag(self) -> None:
        item = {
            "stable_item_key": "teams_recent:chat:thread:message",
            "source_timestamp": "2026-06-28T14:45:00Z",
            "kind": "chat",
            "location": "oneOnOne",
            "sender": "Example Sender",
            "summary": "Can you check this build issue please?",
            "thread_key": "thread",
            "source_id": "message",
        }
        classified = MODULE.classify_teams_item(item)
        self.assertEqual(classified["management_relevance"], "needs_management")
        self.assertIn("FOLLOW_UP", classified["routing_flags"])
        self.assertEqual(classified["closure_state"], "classified")

    def test_teams_self_context_only_message_does_not_become_managed_item(self) -> None:
        item = {
            "surface": "teams_recent",
            "source_type": "chat",
            "source_timestamp": "2026-06-28T14:42:37Z",
            "direction": "self",
            "sender": "Tom Dean-PA",
            "subject_or_location": "oneOnOne",
            "body_preview": "Hi",
            "thread_key": "thread",
            "source_id": "message",
        }
        classified = MODULE.classify_teams_item(item)
        self.assertEqual(classified["management_relevance"], "not_needed")
        self.assertIn("OUTBOUND_CONTEXT", classified["routing_flags"])
        self.assertEqual(classified["closure_state"], "not_needed")

    def test_identityless_event_fails_closed_before_routing(self) -> None:
        event = MODULE.MirrorEvent(
            surface="teams_recent", source_type="chat", direction="inbound",
            sender="Example Sender", subject_or_location="oneOnOne",
            body_preview="Please follow up on the invoice.", raw_evidence_ref="fixture",
        )
        classified = MODULE.classify_mirror_event(event)
        self.assertEqual(classified["stable_item_key"], "teams_recent:chat:no-thread:no-source-id")
        self.assertEqual(classified["management_relevance"], "coverage_incomplete")
        self.assertEqual(classified["route_state"], "coverage_incomplete")
        self.assertEqual(classified["owning_system"], "none")
        self.assertEqual(classified["routing_flags"], [])
        self.assertIn("lacks both provider item ID", classified["reasons"][0])

    def test_canonical_ledger_records_pending_and_coverage_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            event = MODULE.MirrorEvent(
                surface="teams_recent", source_type="chat", source_timestamp="2026-08-27T13:00:00Z",
                thread_key="thread-42", source_id="message-42", raw_evidence_ref="TEAMS_RECENT.md",
            )
            MODULE.persist_canonical_intake_ledger(
                [event], [{"management_relevance": "needs_management", "owning_system": "crm", "candidate_entities": ["Fixture Co"]}],
                MODULE.now_utc(), ledger_root=root,
            )
            MODULE.persist_canonical_intake_ledger(
                [event], [{"management_relevance": "coverage_incomplete", "owning_system": "none", "candidate_entities": []}],
                MODULE.now_utc(), ledger_root=root,
            )
            events = [json.loads(line) for line in (root / "intake-events.jsonl").read_text().splitlines()]
            receipts = [json.loads(line) for line in (root / "intake-route-receipts.jsonl").read_text().splitlines()]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["route_set"], ["coverage", "crm"])
            by_route = {receipt["route"]: receipt for receipt in receipts}
            self.assertEqual(by_route["crm"]["state"], "pending")
            self.assertEqual(by_route["coverage"]["state"], "coverage_incomplete")
            self.assertEqual(by_route["crm"]["attempt"], 1)

    def test_legacy_identityless_state_migration_is_durable_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            router_state_path = root / "mirror-router-state.json"
            monitored_state_path = root / "monitored-items-state.json"
            router_state_path.write_text(json.dumps({"seen": {
                "teams_recent:chat:no-thread:no-source-id": {
                    "surface": "teams_recent",
                    "source_timestamp": None,
                    "first_seen_at": "2026-08-26T10:00:00Z",
                    "last_seen_at": "2026-08-26T10:01:00Z",
                },
                "teams_recent:chat:thread-1:message-1": {"surface": "teams_recent"},
            }}))
            monitored_state_path.write_text(json.dumps({"items": []}))
            old_router_path = MODULE.MIRROR_ROUTER_STATE_PATH
            old_state_path = MODULE.STATE_PATH
            try:
                MODULE.MIRROR_ROUTER_STATE_PATH = router_state_path
                MODULE.STATE_PATH = monitored_state_path
                first = MODULE.migrate_identityless_router_state(write=True)
                second = MODULE.migrate_identityless_router_state(write=True)
            finally:
                MODULE.MIRROR_ROUTER_STATE_PATH = old_router_path
                MODULE.STATE_PATH = old_state_path
            self.assertEqual(first["matched"], 1)
            self.assertTrue(first["written"])
            self.assertEqual(second["matched"], 1)
            state = json.loads(monitored_state_path.read_text())
            self.assertEqual(len(state["items"]), 1)
            entry = state["items"][0]
            self.assertEqual(entry["id"], "teams_recent:chat:no-thread:no-source-id")
            self.assertEqual(entry["closure_state"], "coverage_incomplete")
            self.assertEqual(entry["owning_system"], "none")
            router_state = json.loads(router_state_path.read_text())
            seen = router_state["seen"]["teams_recent:chat:no-thread:no-source-id"]
            self.assertEqual(seen["migration_state"], "legacy_identityless_preserved")

    def test_crm_capture_is_pending_for_one_deterministic_entity(self) -> None:
        event = MODULE.MirrorEvent(
            surface="microsoft_sent", source_type="email", direction="outbound",
            sender="Tom <tom@stackstoneconsulting.co.uk>", participants=["Grant <grant@example.com>"],
            source_id="grant-followup", thread_key="grant-thread", subject_or_location="Call follow-up",
            body_preview="What works for you and Deon?", raw_evidence_ref="fixture",
        )
        item = MODULE.classify_mirror_event(event, entity_candidates=[("Grant Fagan", ["Grant", "grant@example.com"])])
        self.assertEqual(item["owning_system"], "crm")
        self.assertEqual(item["crm_capture_state"], "pending")
        self.assertIsNone(item["crm_capture_blocker"])

    def test_crm_capture_blocks_ambiguous_entity_attribution(self) -> None:
        event = MODULE.MirrorEvent(
            surface="microsoft_inbox", source_type="email", direction="inbound",
            sender="Contact <contact@example.com>", source_id="ambiguous", thread_key="thread",
            subject_or_location="Croyde and NewOrbit", body_preview="Please follow up.", raw_evidence_ref="fixture",
        )
        item = MODULE.classify_mirror_event(event, entity_candidates=[("Croyde Medical", ["Croyde"]), ("NewOrbit Ltd", ["NewOrbit"])])
        self.assertEqual(item["crm_capture_state"], "blocked")
        self.assertIn("multiple candidate entities", item["crm_capture_blocker"])

    def test_sharepoint_folder_alias_resolves_to_display_entity(self) -> None:
        index = MODULE.crm_entity_index()
        self.assertEqual(index["account:Harken"]["entity_name"], "Harken Health")
        self.assertEqual(index["opportunity:ThePracticalCISO"]["entity_name"], "The Practical CISO")
        self.assertEqual(index["partnership:Anuraag Jain - RepoWatch"]["entity_name"], "Anuraag Jain")

    def test_partnership_candidates_are_loaded(self) -> None:
        candidates = MODULE.load_crm_entity_candidates()
        self.assertIn("Grant Fagan", [name for name, _ in candidates])

    def test_sent_surfaces_use_existing_mail_mirrors(self) -> None:
        self.assertEqual(MODULE.SURFACE_SPECS["assistant_sent"]["source_path"], MODULE.ASSISTANT_INBOX_PATH)
        self.assertEqual(MODULE.SURFACE_SPECS["microsoft_sent"]["source_path"], MODULE.MICROSOFT_INBOX_PATH)
        self.assertEqual(MODULE.SURFACE_SPECS["assistant_sent"]["section_heading"], "## Sent Items")
        self.assertEqual(MODULE.SURFACE_SPECS["microsoft_sent"]["section_heading"], "## Sent Items")

    def test_section_scoped_timestamp_extraction_uses_sent_section(self) -> None:
        sample = """## Inbox\n---\nFrom: A <a@example.com> | 2026-06-24 12:00\n\n## Sent Items\n---\nTo: B <b@example.com> | 2026-06-24 09:00\n"""
        ts = MODULE._extract_latest_email_timestamp(sample, heading="## Sent Items")
        self.assertIsNotNone(ts)
        self.assertEqual(ts.strftime("%Y-%m-%d %H:%M"), "2026-06-24 08:00")


class IntakeSurfaceHealthTests(unittest.TestCase):
    def test_health_upsert_covers_every_included_surface_and_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "monitoring-surface-state.json"
            state_path.write_text(json.dumps({"surfaces": {
                "microsoft_inbox": {
                    "coverage_state": "clean",
                    "last_successful_visible_update": "2026-08-27T14:00:00Z",
                    "last_successful_check": "2026-08-27T14:05:00Z",
                },
            }}))
            original = MODULE.SURFACE_STATE_PATH
            try:
                MODULE.SURFACE_STATE_PATH = state_path
                inbox_event = MODULE.MirrorEvent(
                    surface="microsoft_inbox", source_type="email", source_timestamp="2026-08-27T14:30:00Z",
                    thread_key="thread-1", source_id="message-1",
                )
                blocked = {
                    "stable_item_key": "microsoft_inbox:email:thread-1:message-1",
                    "source_timestamp": "2026-08-27T14:30:00Z",
                    "route_state": "coverage_incomplete",
                    "reasons": ["fixture coverage defect"],
                }
                MODULE._upsert_mirror_surface_health(
                    surface_keys=["microsoft_inbox", "assistant_sent"],
                    all_events=[inbox_event],
                    routed_events=[inbox_event],
                    classified=[blocked],
                    attempted_at=MODULE.parse_iso("2026-08-27T15:00:00Z"),
                    duration_ms=37,
                    ledger_root=root,
                )
            finally:
                MODULE.SURFACE_STATE_PATH = original
            rows = json.loads((root / "intake-surface-health.json").read_text())["surfaces"]
            self.assertEqual(set(rows), {"microsoft_inbox", "assistant_sent"})
            inbox = rows["microsoft_inbox"]
            self.assertEqual(inbox["watermark"], "2026-08-27T14:30:00Z")
            self.assertEqual(inbox["last_successful_visible_update"], "2026-08-27T14:00:00Z")
            self.assertEqual(inbox["last_successful_attempt"], "2026-08-27T14:05:00Z")
            self.assertEqual(inbox["captured_count"], 1)
            self.assertEqual(inbox["routed_count"], 1)
            self.assertEqual(inbox["verified_count"], 0)
            self.assertEqual(inbox["blocked_count"], 1)
            self.assertEqual(inbox["oldest_blocker"]["stable_item_key"], blocked["stable_item_key"])
            self.assertEqual(inbox["runtime_duration_ms"], 37)
            self.assertEqual(inbox["coverage_state"], "clean")
            outbound = rows["assistant_sent"]
            self.assertEqual(outbound["coverage_state"], "coverage_incomplete")
            self.assertIsNone(outbound["watermark"])
            self.assertIn("No continuity state", outbound["last_error"])

    def test_health_counts_only_new_events_as_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "monitoring-surface-state.json"
            state_path.write_text(json.dumps({"surfaces": {"teams_recent": {"coverage_state": "blocked", "notes": "fixture failure"}}}))
            first = MODULE.MirrorEvent(surface="teams_recent", source_type="chat", source_timestamp="2026-08-27T12:00:00Z", thread_key="a", source_id="1")
            second = MODULE.MirrorEvent(surface="teams_recent", source_type="chat", source_timestamp="2026-08-27T12:05:00Z", thread_key="b", source_id="2")
            original = MODULE.SURFACE_STATE_PATH
            try:
                MODULE.SURFACE_STATE_PATH = state_path
                MODULE._upsert_mirror_surface_health(
                    surface_keys=["teams_recent"], all_events=[first, second], routed_events=[second],
                    classified=[{"stable_item_key": "teams_recent:chat:b:2", "route_state": "blocked", "source_timestamp": "2026-08-27T12:05:00Z"}],
                    attempted_at=MODULE.parse_iso("2026-08-27T12:10:00Z"), duration_ms=0, ledger_root=root,
                )
            finally:
                MODULE.SURFACE_STATE_PATH = original
            row = json.loads((root / "intake-surface-health.json").read_text())["surfaces"]["teams_recent"]
            self.assertEqual(row["duplicate_count"], 1)
            self.assertEqual(row["coverage_state"], "blocked")
            self.assertEqual(row["last_error"], "fixture failure")

    def test_mirror_report_writes_health_only_with_write_state(self) -> None:
        event = MODULE.MirrorEvent(surface="teams_recent", source_type="chat", thread_key="t", source_id="m")
        with mock.patch.object(MODULE, "build_canonical_mirror_events", return_value=[event]), \
             mock.patch.object(MODULE, "load_mirror_router_state", return_value={"seen": {}}), \
             mock.patch.object(MODULE, "load_crm_entity_candidates", return_value=[]), \
             mock.patch.object(MODULE, "load_live_crm_entity_types", return_value={}), \
             mock.patch.object(MODULE, "classify_mirror_event", return_value={"management_relevance": "not_needed"}), \
             mock.patch.object(MODULE, "_upsert_mirror_surface_health") as health, \
             mock.patch.object(MODULE, "persist_canonical_intake_ledger"), \
             mock.patch.object(MODULE, "build_intake_action_manifest", return_value={"actions": []}), \
             mock.patch.object(MODULE, "_upsert_classified_items_to_state"), \
             mock.patch.object(MODULE, "_mark_events_seen"), \
             mock.patch.object(MODULE, "save_mirror_router_state"):
            MODULE.mirror_routing_report(surface_keys=["teams_recent"], write_state=False)
            health.assert_not_called()
            MODULE.mirror_routing_report(surface_keys=["teams_recent"], write_state=True)
            health.assert_called_once()
            self.assertEqual(health.call_args.kwargs["surface_keys"], ["teams_recent"])


class WhatsAppRetainedWindowTests(unittest.TestCase):
    def test_stale_cursor_before_retained_window_stays_incomplete(self) -> None:
        """A rolling view must not silently rebaseline across evicted WhatsApp events."""
        original_state = MODULE.SURFACE_STATE_PATH
        original_window = MODULE.WHATSAPP_WINDOW_PATH
        original_recent = MODULE.WHATSAPP_RECENT_PATH
        original_spec_path = MODULE.SURFACE_SPECS["whatsapp_recent"]["source_path"]
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                now = MODULE.now_utc().replace(microsecond=0)
                earliest = now - MODULE.timedelta(minutes=30)
                prior = now - MODULE.timedelta(hours=2)
                recent = root / "WHATSAPP_RECENT.md"
                recent.write_text(
                    "# WhatsApp Recent\n"
                    f"_Updated: {now.strftime('%Y-%m-%d %H:%M')}_\n\n"
                    f"[{earliest.strftime('%Y-%m-%d %H:%M')}] Alex: hello\n"
                )
                window = root / "whatsapp-recent-window.json"
                window.write_text(json.dumps({
                    "earliest_retained_source_timestamp": earliest.isoformat().replace("+00:00", "Z"),
                    "latest_retained_source_timestamp": now.isoformat().replace("+00:00", "Z"),
                }))
                state = root / "state.json"
                state.write_text(json.dumps({"surfaces": {"whatsapp_recent": {
                    "surface": "whatsapp_recent",
                    "source_file": "WHATSAPP_RECENT.md",
                    "last_successful_visible_update": prior.isoformat().replace("+00:00", "Z"),
                }}}))
                MODULE.SURFACE_STATE_PATH = state
                MODULE.WHATSAPP_WINDOW_PATH = window
                MODULE.WHATSAPP_RECENT_PATH = recent
                MODULE.SURFACE_SPECS["whatsapp_recent"]["source_path"] = recent

                report = MODULE.whatsapp_continuity_report()
                saved = json.loads(state.read_text())["surfaces"]["whatsapp_recent"]
                self.assertIn("Coverage incomplete", report)
                self.assertEqual(saved["coverage_state"], "incomplete")
                self.assertEqual(saved["last_successful_visible_update"], prior.isoformat().replace("+00:00", "Z"))
        finally:
            MODULE.SURFACE_STATE_PATH = original_state
            MODULE.WHATSAPP_WINDOW_PATH = original_window
            MODULE.WHATSAPP_RECENT_PATH = original_recent
            MODULE.SURFACE_SPECS["whatsapp_recent"]["source_path"] = original_spec_path


if __name__ == "__main__":
    unittest.main()

class WebsiteIntakeLedgerTests(unittest.TestCase):
    def test_website_intake_persists_pending_alert_crm_sharepoint_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = MODULE.normalize_website_intake_item({
                "submission_id": "website-99", "form_type": "lead", "submitted_at": "2026-08-28T05:30:00Z",
                "evidence_ref": "fixture:website-99",
            })
            item = MODULE._classify_canonical_event(event, entity_candidates=[], recent_outbound_addresses=set(), live_entity_types={})
            MODULE.persist_canonical_intake_ledger([event], [item], MODULE.now_utc(), ledger_root=root)
            receipts = [json.loads(line) for line in (root / "intake-route-receipts.jsonl").read_text().splitlines()]
            self.assertEqual({receipt["route"] for receipt in receipts}, {"alert", "crm", "sharepoint"})
            self.assertTrue(all(receipt["state"] == "pending" for receipt in receipts))
            self.assertTrue(all(receipt["destination_ref"] is None for receipt in receipts))
