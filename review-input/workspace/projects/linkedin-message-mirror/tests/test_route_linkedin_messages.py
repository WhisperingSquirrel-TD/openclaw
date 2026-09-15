import importlib.util
import json
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "route_linkedin_messages.py"
spec = importlib.util.spec_from_file_location("route_linkedin_messages", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules["route_linkedin_messages"] = module
spec.loader.exec_module(module)  # type: ignore[union-attr]


def sample_snapshot():
    return {
        "generated_at": "2026-07-06T12:00:00Z",
        "surface": "linkedin_messages",
        "coverage_state": "complete",
        "threads": [
            {
                "thread_key": "linkedin:abc",
                "thread_url": "https://www.linkedin.com/messaging/thread/abc/",
                "participants": [{"name": "Jane Example", "profile_url": "https://www.linkedin.com/in/jane/"}],
                "latest_timestamp": None,
                "latest_timestamp_text": "10:31",
                "latest_direction": "unknown",
                "latest_preview": "Hi Tom, can you follow up on the proposal today?",
                "messages": [
                    {
                        "message_key": "linkedin:abc:m1",
                        "timestamp": None,
                        "timestamp_text": "10:31",
                        "direction": "inbound",
                        "sender": "Jane Example",
                        "body_preview": "Hi Tom, can you follow up on the proposal today?",
                        "body_hash": "sha256:test",
                        "raw_evidence_ref": "memory/linkedin-messages.json#thread_key=linkedin:abc",
                    }
                ],
            }
        ],
    }


def test_snapshot_to_events_emits_canonical_linkedin_event():
    events = module.snapshot_to_events(sample_snapshot())
    assert len(events) == 1
    event = events[0]
    assert event["surface"] == "linkedin_messages"
    assert event["source_type"] == "linkedin_message"
    assert event["direction"] == "inbound"
    assert event["sender"] == "Jane Example"
    assert event["thread_key"] == "linkedin:abc"
    assert event["source_id"] == "linkedin:abc:m1"
    assert event["trust_class"] == "external_social_message"
    assert event["raw_evidence_ref"] == "memory/linkedin-messages.json#thread_key=linkedin:abc"


def test_baseline_then_only_new_suppresses_existing_history(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        snapshot = root / "linkedin-messages.json"
        state = root / "state.json"
        events = root / "events.json"
        proposals = root / "proposals.json"
        proposals_md = root / "proposals.md"
        snapshot.write_text(json.dumps(sample_snapshot()), encoding="utf-8")

        rc = module.main([
            "--snapshot", str(snapshot),
            "--state", str(state),
            "--events-out", str(events),
            "--proposals-out", str(proposals),
            "--proposals-md", str(proposals_md),
            "--baseline", "--write",
        ])
        assert rc == 0
        state_payload = json.loads(state.read_text(encoding="utf-8"))
        assert len(state_payload["seen_item_keys"]) == 1

        rc = module.main([
            "--snapshot", str(snapshot),
            "--state", str(state),
            "--events-out", str(events),
            "--proposals-out", str(proposals),
            "--proposals-md", str(proposals_md),
            "--only-new", "--write",
        ])
        assert rc == 0
        proposal_payload = json.loads(proposals.read_text(encoding="utf-8"))
        assert proposal_payload["new_event_count"] == 0
        assert proposal_payload["proposals"] == []


def test_only_new_routes_new_follow_up_proposal():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        snapshot = root / "linkedin-messages.json"
        state = root / "state.json"
        events = root / "events.json"
        proposals = root / "proposals.json"
        proposals_md = root / "proposals.md"
        snapshot.write_text(json.dumps(sample_snapshot()), encoding="utf-8")

        rc = module.main([
            "--snapshot", str(snapshot),
            "--state", str(state),
            "--events-out", str(events),
            "--proposals-out", str(proposals),
            "--proposals-md", str(proposals_md),
            "--only-new", "--write",
        ])
        assert rc == 0
        proposal_payload = json.loads(proposals.read_text(encoding="utf-8"))
        assert proposal_payload["new_event_count"] == 1
        assert len(proposal_payload["proposals"]) == 1
        assert "FOLLOW_UP" in proposal_payload["proposals"][0]["routing_flags"]
        assert "No LinkedIn CRM/follow-up proposals" not in proposals_md.read_text(encoding="utf-8")
