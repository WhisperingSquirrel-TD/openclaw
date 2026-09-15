import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "capture_linkedin_posts.py"
spec = importlib.util.spec_from_file_location("capture_linkedin_posts", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)  # type: ignore[union-attr]


def raw(author="Tom Dean", url="https://www.linkedin.com/posts/tom-1", stamp="2026-07-22T10:00:00Z", text="A useful post", reactions=1):
    return {"author": author, "url": url, "published_at": stamp, "text": text, "engagement": {"reactions": reactions}}


def test_default_activity_url_is_toms_actual_profile_not_same_name_profile():
    assert module.POSTS_URL == "https://www.linkedin.com/in/tomadean/recent-activity/all/"


def test_author_filter_refuses_non_tom_posts_but_accepts_linkedin_own_post_label():
    assert module.normalize_post(raw(author="Other Person")) is None
    assert module.normalize_post(raw(author="Tom Dean"))["author"] == "Tom Dean"
    assert module.normalize_post(raw(author="Tom Dean · You"))["author"] == "Tom Dean"
    assert module.normalize_post(raw(author="Tom Deanfield · You")) is None


def test_comment_activity_with_two_visible_relative_timestamps_is_not_a_post():
    comment_activity = raw(author="Tom Dean · You")
    comment_activity["relative_activity_count"] = 2
    assert module.normalize_post(comment_activity) is None


def test_compact_linkedin_week_timestamp_is_within_window():
    now = datetime(2026, 7, 23, 12, tzinfo=timezone.utc)
    post = module.normalize_post(raw(stamp="1w · You"))
    assert module.parse_visible_timestamp("1w", now) == now - timedelta(weeks=1)
    assert module.within_refresh_window(post, now)


def test_detail_lookup_uses_only_the_captured_post_permalink_or_urn():
    assert module.detail_url_for_post(raw(url="https://www.linkedin.com/posts/tom-1")) == "https://www.linkedin.com/posts/tom-1"
    assert module.detail_url_for_post(raw(url="", stamp="1w", text="x") | {"urn": "urn:li:activity:7483436749126303744"}) == "https://www.linkedin.com/feed/update/urn:li:activity:7483436749126303744"
    assert module.detail_url_for_post(raw(url="", stamp="1w", text="x") | {"urn": "not-a-linkedin-urn"}) is None


def test_exact_timestamp_requires_visible_iso_evidence_and_normalises_to_utc():
    assert module.exact_iso_timestamp(["1w", "Thursday", "2026-07-16T09:15:32+01:00"]) == "2026-07-16T08:15:32Z"
    assert module.exact_iso_timestamp(["1w", "July 16, 2026"]) is None


def test_activity_urn_supplies_exact_millisecond_timestamp_when_detail_page_omits_it():
    assert module.timestamp_from_activity_urn("urn:li:activity:7483436749126303744") == "2026-07-16T08:25:56Z"
    assert module.timestamp_from_activity_urn("not-an-activity-urn") is None


def test_dedupe_prefers_url_then_fallback_timestamp_and_body_hash():
    first = module.normalize_post(raw())
    changed = module.normalize_post(raw(reactions=5))
    assert len(module.dedupe_posts([first, changed])) == 1
    no_url = module.normalize_post(raw(url="", stamp="2026-07-22T10:00:00Z", text="same"))
    same = module.normalize_post(raw(url="", stamp="2026-07-22T10:00:00Z", text="same"))
    assert module.post_identity(no_url) == module.post_identity(same)


def test_fourteen_day_refresh_boundary_is_inclusive():
    now = datetime(2026, 7, 23, 12, tzinfo=timezone.utc)
    inside = module.normalize_post(raw(stamp=(now - timedelta(days=14)).isoformat().replace("+00:00", "Z")))
    outside = module.normalize_post(raw(url="https://www.linkedin.com/posts/old", stamp=(now - timedelta(days=14, seconds=1)).isoformat().replace("+00:00", "Z")))
    assert module.within_refresh_window(inside, now)
    assert not module.within_refresh_window(outside, now)


def test_engagement_deltas_report_only_changed_visible_counts():
    old, new = module.normalize_post(raw(reactions=2)), module.normalize_post(raw(reactions=7))
    new["engagement"]["comments"] = 3
    assert module.engagement_delta(old, new) == {"reactions": 5, "comments": 3}


def test_incomplete_coverage_preserves_last_clean_anchor_and_raw_snapshot(tmp_path):
    raw_path, state_path = tmp_path / "raw.json", tmp_path / "state.json"
    md_path, tracker_path = tmp_path / "LINKEDIN_POSTS.md", tmp_path / "tracker.md"
    state_path.write_text(json.dumps({"last_successful_visible_capture": "2026-07-22T10:00:00Z"}))
    snapshot = {"generated_at": "2026-07-23T10:00:00Z", "coverage_state": "coverage_incomplete", "blocker": "selector missing", "post_count": 0, "posts": []}
    result = module.reconcile(snapshot, raw_path, tracker_path, md_path, state_path)
    assert result["last_successful_visible_capture"] == "2026-07-22T10:00:00Z"
    assert not raw_path.exists()
    assert "Coverage state: `coverage_incomplete`" in md_path.read_text()


def test_malformed_tracker_fails_closed_without_overwriting_tracker_or_raw_snapshot(tmp_path):
    raw_path, state_path = tmp_path / "raw.json", tmp_path / "state.json"
    md_path, tracker_path = tmp_path / "LINKEDIN_POSTS.md", tmp_path / "tracker.md"
    malformed = "# Tracker| injected row\n"
    tracker_path.write_text(malformed)
    raw_path.write_text(json.dumps({"posts": [module.normalize_post(raw(url="https://www.linkedin.com/posts/old"))]}))
    state_path.write_text(json.dumps({"last_successful_visible_capture": "2026-07-22T10:00:00Z"}))
    snapshot = {"generated_at": "2026-07-23T10:00:00Z", "coverage_state": "complete", "post_count": 1, "posts": [module.normalize_post(raw())]}

    result = module.reconcile(snapshot, raw_path, tracker_path, md_path, state_path)

    assert tracker_path.read_text() == malformed
    assert json.loads(raw_path.read_text())["posts"][0]["url"] == "https://www.linkedin.com/posts/old"
    assert result["last_coverage_state"] == "coverage_incomplete"
    assert result["last_successful_visible_capture"] == "2026-07-22T10:00:00Z"
    assert result["last_blocker"].startswith("tracker_invalid:")


def test_reconciliation_writes_one_tracker_row_and_then_engagement_delta(tmp_path):
    raw_path, state_path = tmp_path / "raw.json", tmp_path / "state.json"
    md_path, tracker_path = tmp_path / "LINKEDIN_POSTS.md", tmp_path / "tracker.md"
    tracker_path.write_text("# Tracker\n\n## Confirmed published\n\n| Published | Title / hook | Theme | Evidence / learning |\n|---|---|---|---|\n\n## Historical theme archive\n")
    post = module.normalize_post(raw())
    snapshot = {"generated_at": "2026-07-23T10:00:00Z", "coverage_state": "complete", "post_count": 1, "posts": [post]}
    assert module.reconcile(snapshot, raw_path, tracker_path, md_path, state_path)["new_post_count"] == 1
    post2 = module.normalize_post(raw(reactions=4))
    snapshot["posts"] = [post2]
    second = module.reconcile(snapshot, raw_path, tracker_path, md_path, state_path)
    assert second["new_post_count"] == 0 and second["updated_engagement_count"] == 1
    tracker_text = tracker_path.read_text()
    assert tracker_text.count("https://www.linkedin.com/posts/tom-1") == 1
    assert "timestamp=2026-07-22T10:00:00Z" in tracker_text
