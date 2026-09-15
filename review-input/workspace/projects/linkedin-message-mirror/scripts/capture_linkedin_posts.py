#!/usr/bin/env python3
"""Bounded, read-only capture/reconciliation of visible Tom-authored LinkedIn posts.

Only visible post cards whose displayed author is exactly ``Tom Dean`` are accepted.
This deliberately fails closed when the authenticated activity surface is incomplete,
logged out, or does not provide enough author evidence. It never performs LinkedIn
writes or visits a general feed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE", "/home/tomdean88/.openclaw/workspace"))
PROFILE_DIR = Path(os.environ.get("LINKEDIN_CAPTURE_PROFILE", "/home/tomdean88/.openclaw/linkedin-browser-profile"))
# Tom's actual public profile slug is ``tomadean``. ``tom-dean`` is a different
# LinkedIn member with the same display name, so never use it as the default.
POSTS_URL = os.environ.get("LINKEDIN_AUTHORED_POSTS_URL", "https://www.linkedin.com/in/tomadean/recent-activity/all/")
RAW_OUT = WORKSPACE / "memory/linkedin-posts-raw.json"
STATE_OUT = WORKSPACE / "memory/linkedin-posts-capture-state.json"
MD_OUT = WORKSPACE / "LINKEDIN_POSTS.md"
TRACKER = WORKSPACE / "stackstone/linkedin-posts.md"
AUTHOR = "Tom Dean"
WINDOW_DAYS = 14
# A detail lookup is deliberately bounded to the visible candidate set. It lets us
# replace LinkedIn's relative activity label (for example ``1w``) with the exact
# timestamp exposed on that individual post, without expanding into a feed/profile
# scrape.
MAX_POST_DETAIL_LOOKUPS = 10


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def body_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(clean(text).encode("utf-8")).hexdigest()


def parse_visible_timestamp(value: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """Parse only unambiguous ISO timestamps or LinkedIn relative day/hour text.

    A visible text timestamp is always retained even when its absolute time cannot
    be safely inferred. The 14-day filter treats unknown timestamps as incomplete.
    """
    value, now = clean(value), now or datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    match = re.fullmatch(r"(\d+)\s*(m|min|minute|h|hour|d|day|w|week)s?\s*(?:ago|[·•].*)?", value, re.I)
    if not match:
        return None
    quantity, unit = int(match.group(1)), match.group(2).lower()
    unit = {"m": "minute", "min": "minute", "h": "hour", "d": "day", "w": "week"}.get(unit, unit)
    return now - timedelta(**{unit + "s": quantity})


def within_refresh_window(post: dict[str, Any], now: Optional[datetime] = None) -> bool:
    timestamp = parse_visible_timestamp(str(post.get("published_at") or post.get("published_timestamp_text") or ""), now)
    return bool(timestamp and timestamp >= (now or datetime.now(timezone.utc)) - timedelta(days=WINDOW_DAYS))


def is_tom_authored_label(value: object) -> bool:
    """Accept LinkedIn's visible own-post labels, including ``Tom Dean · You``.

    The capture is already bounded to Tom's activity/posts surface. This still
    rejects a different person's name rather than accepting a fuzzy match.
    """
    label = clean(value)
    return bool(re.fullmatch(r"Tom Dean(?:\s*(?:[·•]\s*)?You)?", label, re.I))


def detail_url_for_post(raw: dict[str, Any]) -> Optional[str]:
    """Return the single permitted detail route for a captured own-post card."""
    url, urn = clean(raw.get("url")), clean(raw.get("urn"))
    if url:
        return url
    if re.fullmatch(r"urn:li:activity:\d+", urn):
        return f"https://www.linkedin.com/feed/update/{urn}"
    return None


def exact_iso_timestamp(values: list[object]) -> Optional[str]:
    """Choose a visible ISO-8601 timestamp, rejecting vague/localised text."""
    for value in values:
        candidate = clean(value)
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo:
            return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return None


def timestamp_from_activity_urn(value: object) -> Optional[str]:
    """Decode LinkedIn's activity-ID millisecond timestamp, when present.

    Activity IDs are snowflake-style: the upper 41 bits are Unix milliseconds.
    This is used only for an already-captured own-post activity URN and records its
    provenance explicitly; it is not a discovery or API lookup mechanism.
    """
    match = re.fullmatch(r"urn:li:activity:(\d+)", clean(value))
    if not match:
        return None
    millis = int(match.group(1)) >> 22
    try:
        parsed = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_post(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not is_tom_authored_label(raw.get("author")):
        return None
    # The activity/all surface also shows Tom's comments beneath somebody else's
    # post. Those cards contain two visible relative activity timestamps; they are
    # not Tom-authored posts and must not enter the publication tracker.
    if int(raw.get("relative_activity_count") or 0) > 1:
        return None
    text, url, urn = clean(raw.get("text")), clean(raw.get("url")), clean(raw.get("urn"))
    timestamp = clean(raw.get("published_at") or raw.get("published_timestamp_text"))
    # URL/URN is preferred evidence, but a visible timestamp plus body hash is
    # the documented deterministic fallback when LinkedIn omits a permalink.
    if not text or not timestamp:
        return None
    engagement = raw.get("engagement") or {}
    return {
        "author": AUTHOR,
        "url": url or None,
        "urn": urn or None,
        "published_at": timestamp if "T" in timestamp else None,
        "published_timestamp_text": timestamp,
        "published_timestamp_source": clean(raw.get("published_timestamp_source")) or ("visible_iso" if "T" in timestamp else "visible_relative"),
        "text": text,
        "body_hash": body_hash(text),
        "engagement": {key: int(engagement.get(key) or 0) for key in ("reactions", "comments", "reposts", "impressions", "profile_views")},
        "raw_evidence_ref": "memory/linkedin-posts-raw.json",
    }


def post_identity(post: dict[str, Any]) -> tuple[str, str]:
    if post.get("url"):
        return ("url", str(post["url"]))
    if post.get("urn"):
        return ("urn", str(post["urn"]))
    return ("fallback", f"{post.get('published_at') or post.get('published_timestamp_text')}|{post.get('body_hash')}")


def dedupe_posts(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set(); result = []
    for post in posts:
        key = post_identity(post)
        if key not in seen:
            seen.add(key); result.append(post)
    return result


def engagement_delta(old: dict[str, Any], new: dict[str, Any]) -> dict[str, int]:
    before, after = old.get("engagement") or {}, new.get("engagement") or {}
    return {key: int(after.get(key) or 0) - int(before.get(key) or 0) for key in ("reactions", "comments", "reposts", "impressions", "profile_views") if int(after.get(key) or 0) != int(before.get(key) or 0)}


def read_json(path: Path, default: Any) -> Any:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def operator_markdown(snapshot: dict[str, Any], changes: list[dict[str, Any]]) -> str:
    lines = ["# LINKEDIN_POSTS.md", "", f"_Generated: {snapshot.get('generated_at')}_", "", f"- Coverage state: `{snapshot.get('coverage_state')}`", f"- Visible authored posts: {snapshot.get('post_count', 0)}", f"- New posts: {sum(c['kind'] == 'new' for c in changes)}", f"- Engagement updates: {sum(c['kind'] == 'engagement' for c in changes)}"]
    if snapshot.get("blocker"): lines.append(f"- Blocker: {snapshot['blocker']}")
    lines.extend(["", "## Visible posts", ""])
    for post in snapshot.get("posts", []):
        lines.extend([f"### {post['published_timestamp_text']}", f"- URL/URN: {post.get('url') or post.get('urn')}", f"- Text: {clean(post['text'])[:280]}", f"- Engagement: {post['engagement']}", ""])
    return "\n".join(lines)


def tracker_row(post: dict[str, Any]) -> str:
    date = (post.get("published_at") or post["published_timestamp_text"]).split("T")[0]
    hook = clean(post["text"]).split(".")[0][:100].replace("|", "\\|")
    evidence = f"Mirror-confirmed: {post.get('url') or post.get('urn')}; timestamp={post['published_timestamp_text']}; timestamp_source={post.get('published_timestamp_source')}; body_hash={post['body_hash']}; engagement={post['engagement']}"
    return f"| {date} | {hook} | Mirror-confirmed authored post | {evidence} |"


def replace_tracker_row(tracker: str, post: dict[str, Any]) -> str:
    """Refresh the existing canonical row when stronger evidence arrives."""
    identifier = re.escape(str(post.get("url") or post.get("urn") or ""))
    if not identifier:
        return tracker
    return re.sub(rf"(?m)^\|[^\n]*{identifier}[^\n]*\|$", tracker_row(post), tracker)


def tracker_has_post(tracker: str, post: dict[str, Any]) -> bool:
    identifier = post.get("url") or post.get("urn")
    return bool((identifier and str(identifier) in tracker) or (post["published_timestamp_text"] in tracker and post["body_hash"] in tracker))


def valid_tracker(tracker: str) -> bool:
    """Only reconcile into the canonical tracker when its required table is intact.

    A damaged tracker is evidence risk, not an invitation to append more rows into
    prose. The caller fails closed and retains the previous raw/tracker snapshot.
    """
    return bool(re.search(
        r"(?m)^## Confirmed published\n\n\| Published \| Title / hook \| Theme \| Evidence / learning \|\n\|---\|---\|---\|---\|$",
        tracker,
    ))


def reconcile(snapshot: dict[str, Any], raw_path: Path, tracker_path: Path, md_path: Path, state_path: Path) -> dict[str, Any]:
    prior_state = read_json(state_path, {})
    effective_snapshot = dict(snapshot)
    tracker = tracker_path.read_text(encoding="utf-8") if tracker_path.exists() else "# Stackstone LinkedIn Post Tracker\n\n## Confirmed published\n\n| Published | Title / hook | Theme | Evidence / learning |\n|---|---|---|---|\n\n## Historical theme archive\n"
    if snapshot.get("coverage_state") == "complete" and not valid_tracker(tracker):
        effective_snapshot["coverage_state"] = "coverage_incomplete"
        effective_snapshot["blocker"] = "tracker_invalid: canonical tracker structure is malformed; no reconciliation write performed"

    previous = read_json(raw_path, {"posts": []})
    previous_by_id = {post_identity(p): p for p in previous.get("posts", [])}
    changes: list[dict[str, Any]] = []
    if effective_snapshot.get("coverage_state") == "complete":
        insert_at = tracker.find("\n## Historical theme archive")
        for post in effective_snapshot["posts"]:
            old = previous_by_id.get(post_identity(post))
            if old is None:
                changes.append({"kind": "new", "post": post})
                if not tracker_has_post(tracker, post):
                    row = tracker_row(post) + "\n"
                    tracker = tracker[:insert_at] + row + tracker[insert_at:] if insert_at >= 0 else tracker + "\n" + row
            else:
                delta = engagement_delta(old, post)
                if delta: changes.append({"kind": "engagement", "post": post, "delta": delta})
            # The same activity URN must remain one row, but a later capture may
            # replace a relative timestamp/body snapshot with stronger evidence.
            if tracker_has_post(tracker, post):
                tracker = replace_tracker_row(tracker, post)
        tracker_path.write_text(tracker, encoding="utf-8")
        write_json(raw_path, effective_snapshot)
    state = {"updated_at": utc_now(), "last_coverage_state": effective_snapshot.get("coverage_state"), "last_blocker": effective_snapshot.get("blocker"), "last_successful_visible_capture": effective_snapshot.get("generated_at") if effective_snapshot.get("coverage_state") == "complete" else prior_state.get("last_successful_visible_capture"), "post_count": effective_snapshot.get("post_count", 0), "new_post_count": sum(c["kind"] == "new" for c in changes), "updated_engagement_count": sum(c["kind"] == "engagement" for c in changes)}
    write_json(state_path, state); md_path.write_text(operator_markdown(effective_snapshot, changes), encoding="utf-8")
    return {**state, "changes": changes}


def extract_visible_posts(page: Any) -> list[dict[str, Any]]:
    return page.evaluate(r'''() => Array.from(document.querySelectorAll('article, .feed-shared-update-v2')).map(el => {
      const text = (el.innerText || '').replace(/\s+/g, ' ').trim();
      const links = Array.from(el.querySelectorAll('a[href]')).map(a => a.href || '');
      const url = links.find(h => /\/posts\//.test(h)) || '';
      const urn = el.getAttribute('data-urn') || el.getAttribute('data-id') || '';
      const labels = Array.from(el.querySelectorAll('a, span')).map(x => (x.innerText || '').replace(/\s+/g, ' ').trim());
      const author = labels.find(x => /^Tom Dean(?:\s*(?:[·•]\s*)?You)?$/i.test(x)) || '';
      // LinkedIn's activity cards currently expose relative time as card text
      // (for example `1w · 1 week ago`) rather than a <time> element.
      const time = (el.querySelector('time')?.getAttribute('datetime') || el.querySelector('time')?.innerText || (text.match(/\b\d+\s*(?:m|min|minute|h|hour|d|day|w|week)s?\b/i) || [''])[0]);
      const number = label => { const m = text.match(new RegExp('(\\d[\\d,.]*)\\s+' + label, 'i')); return m ? Number(m[1].replace(/[,\.](?=\d{3}\b)/g, '')) : 0; };
      const relativeActivityCount = (text.match(/\b\d+\s*(?:m|min|minute|h|hour|d|day|w|week)s?\s*[·•]/gi) || []).length;
      return {author, url, urn, published_at: time, text, relative_activity_count: relativeActivityCount, engagement: {reactions:number('reactions?'), comments:number('comments?'), reposts:number('reposts?'), impressions:number('impressions'), profile_views:number('profile views')}};
    })''')


def enrich_with_exact_timestamps(context: Any, raw_posts: list[dict[str, Any]], args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """Look up an exact visible timestamp for each bounded own-post candidate.

    The activity surface is used only to discover Tom-authored cards. Every lookup
    below is then restricted to that card's own permalink/URN route; no discovery,
    scrolling, or profile expansion occurs here. A missing exact timestamp is an
    evidence failure, not permission to invent one from ``1w``.
    """
    enriched: list[dict[str, Any]] = []
    failures: list[str] = []
    diagnostics: list[dict[str, Any]] = []
    for raw in raw_posts[:MAX_POST_DETAIL_LOOKUPS]:
        target = detail_url_for_post(raw)
        identifier = clean(raw.get("urn") or raw.get("url") or "unknown")
        if not target:
            failures.append(f"detail_route_missing:{identifier}")
            continue
        detail = context.new_page()
        try:
            detail.goto(target, wait_until="domcontentloaded", timeout=args.timeout_ms)
            detail.wait_for_timeout(args.settle_ms)
            evidence = detail.evaluate(r'''() => {
              const values = [];
              const add = value => { if (typeof value === 'string' && value.trim()) values.push(value.trim()); };
              document.querySelectorAll('time').forEach(el => [el.getAttribute('datetime'), el.getAttribute('title'), el.getAttribute('aria-label'), el.innerText].forEach(add));
              document.querySelectorAll('meta[property="article:published_time"], meta[itemprop="datePublished"], meta[name="date"]')
                .forEach(el => add(el.getAttribute('content')));
              const walk = value => {
                if (!value || typeof value !== 'object') return;
                if (Array.isArray(value)) return value.forEach(walk);
                ['datePublished', 'uploadDate', 'dateCreated'].forEach(key => add(value[key]));
                Object.values(value).forEach(walk);
              };
              document.querySelectorAll('script[type="application/ld+json"]').forEach(el => { try { walk(JSON.parse(el.textContent || '')); } catch (_) {} });
              return { values: [...new Set(values)].slice(0, 30), time_elements: document.querySelectorAll('time').length, final_url: location.href };
            }''')
            exact = exact_iso_timestamp(evidence.get("values", []))
            source = "detail_page_visible_iso" if exact else "activity_urn_snowflake"
            if not exact:
                exact = timestamp_from_activity_urn(raw.get("urn"))
            diagnostics.append({"post": identifier, "final_url": evidence.get("final_url"), "time_element_count": evidence.get("time_elements", 0), "timestamp_candidate_count": len(evidence.get("values", [])), "exact_timestamp_found": bool(exact), "timestamp_source": source if exact else None})
            if not exact:
                failures.append(f"exact_timestamp_missing:{identifier}")
                continue
            item = dict(raw)
            item["published_at"] = exact
            item["published_timestamp_source"] = source
            enriched.append(item)
        except Exception as exc:
            failures.append(f"detail_lookup_failed:{identifier}:{type(exc).__name__}")
            diagnostics.append({"post": identifier, "detail_lookup_error": type(exc).__name__})
        finally:
            detail.close()
    if len(raw_posts) > MAX_POST_DETAIL_LOOKUPS:
        failures.append(f"detail_lookup_limit_exceeded:{len(raw_posts)}>{MAX_POST_DETAIL_LOOKUPS}")
    return enriched, failures, diagnostics


def capture(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {"generated_at": utc_now(), "surface": "linkedin_authored_posts", "coverage_state": "blocked", "blocker": f"dependency_missing: {exc}", "posts": [], "post_count": 0}
    if WORKSPACE in PROFILE_DIR.parents: return {"generated_at": utc_now(), "surface": "linkedin_authored_posts", "coverage_state": "blocked", "blocker": "profile_dir_inside_workspace_refused", "posts": [], "post_count": 0}
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=not args.headed, viewport={"width": 1400, "height": 1000})
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(POSTS_URL, wait_until="domcontentloaded", timeout=args.timeout_ms); page.wait_for_timeout(args.settle_ms)
            if "login" in page.url.lower() or "signup" in page.url.lower():
                return {"generated_at": utc_now(), "surface": "linkedin_authored_posts", "coverage_state": "login_required", "blocker": "LinkedIn login required", "posts": [], "post_count": 0}
            raw_cards = extract_visible_posts(page)
            author_cards = [raw for raw in raw_cards if is_tom_authored_label(raw.get("author"))]
            candidate_cards = [raw for raw in author_cards if normalize_post(raw) and within_refresh_window(normalize_post(raw))]
            exact_cards, timestamp_failures, detail_diagnostics = enrich_with_exact_timestamps(context, candidate_cards, args)
            normalised = [post for raw in exact_cards if (post := normalize_post(raw))]
            posts = dedupe_posts([post for post in normalised if within_refresh_window(post)])
            # Exact publication time is a required evidence field for this mirror.
            # A partial detail pass must fail closed rather than silently retaining
            # relative labels or reconciling an incomplete publication record.
            state = "complete" if posts and not timestamp_failures and len(posts) == len(candidate_cards) else "coverage_incomplete"
            blocker = None if state == "complete" else ("; ".join(timestamp_failures) if timestamp_failures else "No verified Tom-authored posts with exact visible timestamp in the 14-day window")
            return {"generated_at": utc_now(), "surface": "linkedin_authored_posts", "coverage_state": state, "capture_mode": "playwright_persistent_profile", "refresh_window_days": WINDOW_DAYS, "blocker": blocker, "diagnostics": {"visible_card_count": len(raw_cards), "tom_author_card_count": len(author_cards), "candidate_post_card_count": len(candidate_cards), "normalised_post_count": len(normalised), "exact_timestamp_count": len(posts), "detail_lookup_failure_count": len(timestamp_failures), "detail_lookups": detail_diagnostics}, "post_count": len(posts), "posts": posts}
        except Exception as exc:
            return {"generated_at": utc_now(), "surface": "linkedin_authored_posts", "coverage_state": "blocked", "blocker": f"capture_exception: {type(exc).__name__}: {exc}", "posts": [], "post_count": 0}
        finally: context.close()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only bounded LinkedIn authored-post capture")
    parser.add_argument("--write", action="store_true"); parser.add_argument("--reconcile", action="store_true"); parser.add_argument("--headed", action="store_true")
    parser.add_argument("--timeout-ms", type=int, default=45000); parser.add_argument("--settle-ms", type=int, default=5000)
    parser.add_argument("--raw-out", default=str(RAW_OUT)); parser.add_argument("--state-out", default=str(STATE_OUT)); parser.add_argument("--md-out", default=str(MD_OUT)); parser.add_argument("--tracker", default=str(TRACKER))
    args = parser.parse_args(argv); snapshot = capture(args)
    result: dict[str, Any] = {"snapshot": snapshot}
    if args.write or args.reconcile: result["reconciliation"] = reconcile(snapshot, Path(args.raw_out), Path(args.tracker), Path(args.md_out), Path(args.state_out))
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
