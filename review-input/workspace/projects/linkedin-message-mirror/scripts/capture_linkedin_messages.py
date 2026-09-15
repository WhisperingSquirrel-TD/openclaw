#!/usr/bin/env python3
"""Local read-only LinkedIn message capture proof.

MVP constraints:
- read-only browser navigation only;
- no sending, connection requests, reactions, or downloads;
- headed/manual-first;
- persistent browser profile lives outside the workspace by default;
- writes deterministic JSON + compact markdown status artifacts.

This is intentionally conservative. It captures visible message-list/thread preview
signals and fails closed to `login_required`, `dependency_missing`, `blocked`, or
`coverage_incomplete` rather than making strong claims from weak evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE", "/home/tomdean88/.openclaw/workspace"))
DEFAULT_PROFILE_DIR = Path(os.environ.get("LINKEDIN_CAPTURE_PROFILE", "/home/tomdean88/.openclaw/linkedin-browser-profile"))
DEFAULT_JSON_OUT = WORKSPACE / "memory" / "linkedin-messages.json"
DEFAULT_MD_OUT = WORKSPACE / "LINKEDIN_MESSAGES.md"
DEFAULT_STATE_OUT = WORKSPACE / "memory" / "linkedin-capture-state.json"
LINKEDIN_MESSAGES_URL = "https://www.linkedin.com/messaging/"

LOG_SUBSYSTEM = "linkedin-message-mirror"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:16]


def sanitize_space(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def body_preview(value: str, max_chars: int = 240) -> str:
    value = sanitize_space(value)
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "…"


def structured_log(action: str, outcome: str, **fields: Any) -> None:
    event = {
        "timestamp": utc_now(),
        "level": "info" if outcome in {"ok", "blocked", "login_required", "dependency_missing"} else "error",
        "subsystem": LOG_SUBSYSTEM,
        "action": action,
        "outcome": outcome,
        **fields,
    }
    print(json.dumps(event, ensure_ascii=False), flush=True)


def make_empty_snapshot(coverage_state: str, blocker: Optional[str] = None, capture_mode: str = "playwright_persistent_profile") -> Dict[str, Any]:
    return {
        "generated_at": utc_now(),
        "surface": "linkedin_messages",
        "coverage_state": coverage_state,
        "capture_mode": capture_mode,
        "blocker": blocker,
        "thread_count": 0,
        "message_count": 0,
        "threads": [],
    }


def make_thread_key(thread_url: str, participant_names: List[str], preview: str) -> str:
    raw = "|".join([thread_url, ",".join(participant_names), preview])
    return f"linkedin:{stable_hash(raw)}"


def normalize_thread(raw: Dict[str, Any]) -> Dict[str, Any]:
    thread_url = sanitize_space(raw.get("thread_url"))
    names = [sanitize_space(x) for x in raw.get("participant_names", []) if sanitize_space(x)]
    if not names and raw.get("title"):
        names = [sanitize_space(raw.get("title"))]
    latest_preview = body_preview(raw.get("latest_preview", ""))
    thread_key = make_thread_key(thread_url, names, latest_preview)
    latest_timestamp_text = sanitize_space(raw.get("latest_timestamp_text"))
    direction = "outbound" if latest_preview.lower().startswith("you:") else "unknown"

    message_key = f"{thread_key}:{stable_hash(latest_timestamp_text + '|' + latest_preview)}"
    message = {
        "message_key": message_key,
        "timestamp": None,
        "timestamp_text": latest_timestamp_text,
        "direction": direction,
        "sender": "Tom Dean" if direction == "outbound" else (names[0] if names else "unknown"),
        "body_preview": latest_preview,
        "body_hash": f"sha256:{hashlib.sha256(latest_preview.encode('utf-8')).hexdigest()}" if latest_preview else None,
        "raw_evidence_ref": f"memory/linkedin-messages.json#thread_key={thread_key}",
    }

    return {
        "thread_key": thread_key,
        "thread_url": thread_url or None,
        "participants": [{"name": n, "profile_url": None, "headline_or_company": None} for n in names],
        "latest_timestamp": None,
        "latest_timestamp_text": latest_timestamp_text or None,
        "latest_direction": direction,
        "latest_preview": latest_preview,
        "messages": [message] if latest_preview or latest_timestamp_text or names else [],
    }


def snapshot_to_markdown(snapshot: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# LINKEDIN_MESSAGES.md")
    lines.append("")
    lines.append(f"_Generated: {snapshot.get('generated_at')}_")
    lines.append("")
    lines.append(f"- Surface: `{snapshot.get('surface', 'linkedin_messages')}`")
    lines.append(f"- Coverage state: `{snapshot.get('coverage_state')}`")
    lines.append(f"- Capture mode: `{snapshot.get('capture_mode')}`")
    if snapshot.get("blocker"):
        lines.append(f"- Blocker: {snapshot.get('blocker')}")
    if snapshot.get("retry_policy"):
        lines.append(f"- Retry policy: {snapshot.get('retry_policy')}")
    if snapshot.get("next_pass_mode"):
        lines.append(f"- Next pass mode: `{snapshot.get('next_pass_mode')}`")
    diagnostics = snapshot.get("diagnostics") or {}
    if diagnostics:
        lines.append(f"- Diagnostics: url=`{diagnostics.get('url', '')}`, title=`{diagnostics.get('title', '')}`, message_items={diagnostics.get('message_item_count', 'n/a')}, body_chars={diagnostics.get('body_text_chars', 'n/a')}")
    lines.append(f"- Threads captured: {snapshot.get('thread_count', 0)}")
    lines.append(f"- Message previews captured: {snapshot.get('message_count', 0)}")
    lines.append("")

    if not snapshot.get("threads"):
        lines.append("No LinkedIn message threads captured in this pass.")
        lines.append("")
        return "\n".join(lines)

    lines.append("## Recent visible threads")
    lines.append("")
    for thread in snapshot["threads"]:
        participants = ", ".join(p.get("name", "unknown") for p in thread.get("participants", [])) or "unknown"
        lines.append(f"### {participants}")
        lines.append(f"- Thread key: `{thread.get('thread_key')}`")
        if thread.get("thread_url"):
            lines.append(f"- URL: {thread.get('thread_url')}")
        if thread.get("latest_timestamp_text"):
            lines.append(f"- Visible timestamp: {thread.get('latest_timestamp_text')}")
        if thread.get("latest_preview"):
            lines.append(f"- Preview: {thread.get('latest_preview')}")
        lines.append("")
    return "\n".join(lines)


def write_outputs(snapshot: Dict[str, Any], json_out: Path, md_out: Path) -> None:
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_out.write_text(snapshot_to_markdown(snapshot), encoding="utf-8")


def read_capture_state(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"consecutive_failures": 0, "next_pass_mode": "normal"}


def write_capture_state(path: Path, snapshot: Dict[str, Any]) -> None:
    previous = read_capture_state(path)
    failed = snapshot.get("coverage_state") != "complete"
    payload = {
        "updated_at": utc_now(),
        "last_coverage_state": snapshot.get("coverage_state"),
        "last_blocker": snapshot.get("blocker"),
        "consecutive_failures": (int(previous.get("consecutive_failures") or 0) + 1) if failed else 0,
        "next_pass_mode": "diagnostic" if failed else "normal",
        "last_diagnostics": snapshot.get("diagnostics") or {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def capture_diagnostics(page: Any) -> Dict[str, Any]:
    js = r"""() => {
      const body = document.body;
      const bodyText = (body && body.innerText || '').replace(/\s+/g, ' ').trim();
      return {
        url: window.location.href,
        title: document.title,
        ready_state: document.readyState,
        html_chars: (document.documentElement && document.documentElement.outerHTML || '').length,
        body_html_chars: (body && body.innerHTML || '').length,
        message_item_count: document.querySelectorAll('.msg-conversation-listitem').length,
        thread_anchor_count: document.querySelectorAll('a[href*="/messaging/thread/"]').length,
        body_text_chars: bodyText.length,
        body_text_sample: bodyText.slice(0, 1200),
      };
    }"""
    try:
        diagnostics = dict(page.evaluate(js) or {})
        diagnostics["frame_count"] = len(page.frames)
        diagnostics["frame_urls"] = [frame.url for frame in page.frames[:5]]
        return diagnostics
    except Exception as exc:
        return {"diagnostic_error": f"{type(exc).__name__}: {exc}"}


def wait_for_message_document(page: Any, timeout_ms: int) -> Dict[str, Any]:
    """Boundedly wait for usable LinkedIn content without treating blank as empty."""
    domcontentloaded = "ok"
    try:
        page.wait_for_load_state("domcontentloaded", timeout=min(timeout_ms, 10000))
    except Exception as exc:
        domcontentloaded = f"{type(exc).__name__}: {exc}"
    try:
        page.wait_for_function(
            """() => {
              const body = document.body;
              if (!body) return false;
              const hasMessagingShell = Boolean(document.querySelector(
                '.msg-conversations-container, .msg-conversation-listitem, [data-view-name*="messaging"]'
              ));
              return hasMessagingShell || body.innerText.trim().length > 0;
            }""",
            timeout=max(1000, min(timeout_ms, 15000)),
        )
        ready = True
        readiness_error = None
    except Exception as exc:
        ready = False
        readiness_error = f"{type(exc).__name__}: {exc}"
    diagnostics = capture_diagnostics(page)
    diagnostics["document_ready"] = ready
    diagnostics["domcontentloaded"] = domcontentloaded
    if readiness_error:
        diagnostics["readiness_error"] = readiness_error
    return diagnostics


def bootstrap_messaging_via_feed(page: Any, timeout_ms: int) -> Dict[str, Any]:
    """Recover a stuck direct messaging navigation through LinkedIn's feed shell."""
    feed_url = "https://www.linkedin.com/feed/"
    page.goto(feed_url, wait_until="commit", timeout=timeout_ms)
    try:
        page.wait_for_function(
            "() => document.body && document.body.innerText.trim().length > 0",
            timeout=max(1000, min(timeout_ms, 15000)),
        )
    except Exception:
        # The following messaging navigation remains the proof gate.
        pass
    page.goto(LINKEDIN_MESSAGES_URL, wait_until="commit", timeout=timeout_ms)
    diagnostics = wait_for_message_document(page, timeout_ms)
    diagnostics["recovery_route"] = "feed_then_messaging"
    return diagnostics


def import_playwright():
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local env
        return None, exc
    return sync_playwright, None


def extract_visible_threads(page: Any, limit_threads: int) -> List[Dict[str, Any]]:
    """Extract visible message-list items using conservative DOM heuristics.

    LinkedIn has recently stopped exposing stable /messaging/thread/ anchors in
    the conversation list. Keep the old anchor path, then fall back to visible
    list-item text from the current messaging UI. This remains read-only and
    captures only visible previews.
    """
    js = r"""
    (limit) => {
      function clean(x) { return (x || '').replace(/\s+/g, ' ').trim(); }
      function linesFor(el) {
        return (el.innerText || '')
          .split('\n')
          .map(x => clean(x))
          .filter(Boolean)
          .filter(x => !/^Status is reachable$/i.test(x))
          .filter(x => !/^\. Press return/i.test(x))
          .filter(x => !/^Open the options list/i.test(x));
      }
      function timestampFrom(lines) {
        return lines.find(x => /^(now|\d+[smhdw]|\d{1,2}:\d{2}\s*(am|pm)?|mon|tue|wed|thu|fri|sat|sun|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|yesterday)/i.test(x)) || '';
      }
      const seen = new Set();
      const rows = [];

      const anchors = Array.from(document.querySelectorAll('a[href*="/messaging/thread/"]'));
      for (const a of anchors) {
        const href = a.href || '';
        if (!href || seen.has(href)) continue;
        seen.add(href);
        const container = a.closest('li, .msg-conversation-listitem, [data-view-name], div') || a;
        const lines = linesFor(container);
        const title = lines[0] || '';
        const timestamp = timestampFrom(lines);
        const preview = lines.slice(1).filter(x => x !== timestamp).join(' · ');
        if (title || preview) rows.push({
          thread_url: href,
          title,
          participant_names: title ? [title] : [],
          latest_timestamp_text: timestamp,
          latest_preview: preview,
        });
        if (rows.length >= limit) return rows;
      }

      const msgItems = Array.from(document.querySelectorAll('.msg-conversation-listitem'));
      const candidates = msgItems.length ? msgItems : Array.from(document.querySelectorAll('li[class*="msg-conversation"], [role="listitem"]'));
      for (const el of candidates) {
        const raw = clean(el.innerText || '');
        if (!raw || raw.length < 8) continue;
        const lines = linesFor(el);
        if (!lines.length) continue;
        const activeIdx = lines.findIndex(x => /Active conversation/i.test(x));
        const useful = activeIdx >= 0 ? lines.slice(0, activeIdx) : lines;
        const title = useful[0] || '';
        const timestamp = timestampFrom(useful.slice(1));
        const preview = useful
          .slice(1)
          .filter(x => x !== timestamp)
          .filter((x, idx, arr) => idx === 0 || x !== arr[idx - 1])
          .filter(x => !/^Focused$/i.test(x) && !/^Jobs Unread Connections InMail Starred$/i.test(x))
          .join(' · ');
        const key = `${title}|${timestamp}|${preview}`;
        if (!title || /^Status is (online|reachable)$/i.test(title) || seen.has(key)) continue;
        seen.add(key);
        rows.push({
          thread_url: '',
          title,
          participant_names: [title],
          latest_timestamp_text: timestamp,
          latest_preview: preview || raw,
        });
        if (rows.length >= limit) break;
      }
      return rows;
    }
    """
    return page.evaluate(js, limit_threads)


def run_capture(args: argparse.Namespace) -> Dict[str, Any]:
    started = time.time()
    sync_playwright, import_error = import_playwright()
    if import_error:
        snapshot = make_empty_snapshot("blocked", f"dependency_missing: playwright is not installed/importable ({import_error})")
        structured_log("capture", "dependency_missing", duration_ms=int((time.time() - started) * 1000), blocker=snapshot["blocker"])
        return snapshot

    profile_dir = Path(args.profile_dir).expanduser()
    if WORKSPACE in profile_dir.parents or profile_dir == WORKSPACE:
        snapshot = make_empty_snapshot("blocked", "profile_dir_inside_workspace_refused")
        structured_log("capture", "blocked", duration_ms=int((time.time() - started) * 1000), blocker=snapshot["blocker"])
        return snapshot

    profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser_name = args.browser
        browser_type = getattr(p, browser_name)
        context = browser_type.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=not args.headed,
            viewport={"width": 1400, "height": 1000},
        )
        page = context.pages[0] if context.pages else context.new_page()
        browser_events: List[str] = []
        page_errors: List[str] = []
        page.on("console", lambda msg: browser_events.append(f"{msg.type}: {msg.text}") if msg.type in {"error", "warning"} else None)
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        try:
            # LinkedIn's messaging SPA may keep loading resources after the document is
            # usable. Waiting for domcontentloaded caused the whole capture to time out
            # even when the committed page could have been inspected. Commit is enough
            # for this read-only visible-DOM capture; extraction retries below remain the
            # coverage gate. Bound navigation separately from the overall helper timeout.
            navigation_timeout_ms = min(args.timeout_ms, 30000)
            page.goto(LINKEDIN_MESSAGES_URL, wait_until="commit", timeout=navigation_timeout_ms)
            readiness_diagnostics = wait_for_message_document(page, navigation_timeout_ms)
            page.wait_for_timeout(args.settle_ms)

            # LinkedIn occasionally leaves a direct /messaging/ navigation on its
            # loading skeleton while the authenticated feed shell boots normally.
            # Recover only from that proven blank state; do not interpret it as an
            # empty inbox or change any message selectors.
            if not readiness_diagnostics.get("document_ready"):
                readiness_diagnostics = bootstrap_messaging_via_feed(page, navigation_timeout_ms)
                page.wait_for_timeout(args.settle_ms)

            current_url = page.url
            title = page.title()
            if "login" in current_url.lower() or "signup" in current_url.lower() or "linkedin" not in current_url.lower():
                if args.headed and args.login_wait_seconds > 0:
                    structured_log(
                        "login_wait",
                        "login_required",
                        duration_ms=int((time.time() - started) * 1000),
                        url=current_url,
                        title=title,
                        wait_seconds=args.login_wait_seconds,
                    )
                    deadline = time.time() + args.login_wait_seconds
                    while time.time() < deadline:
                        page.wait_for_timeout(2000)
                        current_url = page.url
                        if "login" not in current_url.lower() and "signup" not in current_url.lower() and "linkedin" in current_url.lower():
                            page.wait_for_timeout(args.settle_ms)
                            break
                    current_url = page.url
                    title = page.title()
                if "login" in current_url.lower() or "signup" in current_url.lower() or "linkedin" not in current_url.lower():
                    snapshot = make_empty_snapshot("login_required", f"LinkedIn login required or unexpected URL: {current_url}")
                    structured_log("capture", "login_required", duration_ms=int((time.time() - started) * 1000), url=current_url, title=title)
                    return snapshot

            prior_state = read_capture_state(Path(args.state_out))
            diagnostic_mode = (prior_state.get("next_pass_mode") == "diagnostic") or bool(args.diagnostic)
            attempts = max(1, args.retry_attempts + (1 if diagnostic_mode else 0))
            raw_threads: List[Dict[str, Any]] = []
            diagnostics: Dict[str, Any] = {}
            for attempt in range(1, attempts + 1):
                raw_threads = extract_visible_threads(page, args.limit_threads)
                if raw_threads:
                    break
                diagnostics = capture_diagnostics(page)
                diagnostics["initial_readiness"] = readiness_diagnostics
                diagnostics["browser_events"] = browser_events[-20:]
                diagnostics["page_errors"] = page_errors[-20:]
                structured_log(
                    "capture_retry",
                    "coverage_incomplete",
                    attempt=attempt,
                    attempts=attempts,
                    message_item_count=diagnostics.get("message_item_count"),
                    url=diagnostics.get("url") or page.url,
                )
                if attempt < attempts:
                    try:
                        page.reload(wait_until="commit", timeout=navigation_timeout_ms)
                    except Exception:
                        page.goto(LINKEDIN_MESSAGES_URL, wait_until="commit", timeout=navigation_timeout_ms)
                    readiness_diagnostics = wait_for_message_document(page, navigation_timeout_ms)
                    if not readiness_diagnostics.get("document_ready"):
                        readiness_diagnostics = bootstrap_messaging_via_feed(page, navigation_timeout_ms)
                    page.wait_for_timeout(args.settle_ms + (2000 if diagnostic_mode else 0))

            threads = [normalize_thread(t) for t in raw_threads]
            message_count = sum(len(t.get("messages", [])) for t in threads)
            coverage_state = "complete" if threads else "coverage_incomplete"
            blocker = None if threads else "No visible LinkedIn messaging threads captured after retry; alert Tom and run next pass in diagnostic mode."
            if coverage_state != "complete" and not diagnostics:
                diagnostics = capture_diagnostics(page)
                diagnostics["initial_readiness"] = readiness_diagnostics
                diagnostics["browser_events"] = browser_events[-20:]
                diagnostics["page_errors"] = page_errors[-20:]
            snapshot = {
                "generated_at": utc_now(),
                "surface": "linkedin_messages",
                "coverage_state": coverage_state,
                "capture_mode": "playwright_persistent_profile",
                "blocker": blocker,
                "retry_policy": "retried before fail; failed pass sets next_pass_mode=diagnostic",
                "retry_attempts": attempts,
                "next_pass_mode": "normal" if coverage_state == "complete" else "diagnostic",
                "diagnostics": diagnostics,
                "thread_count": len(threads),
                "message_count": message_count,
                "threads": threads,
            }
            structured_log(
                "capture",
                "ok" if threads else "coverage_incomplete",
                duration_ms=int((time.time() - started) * 1000),
                retry_attempts=attempts,
                thread_count=len(threads),
                message_count=message_count,
                url=current_url,
                next_pass_mode=snapshot.get("next_pass_mode"),
            )
            return snapshot
        except Exception as exc:  # pragma: no cover - live browser dependent
            snapshot = make_empty_snapshot("blocked", f"capture_exception: {type(exc).__name__}: {exc}")
            structured_log("capture", "blocked", duration_ms=int((time.time() - started) * 1000), blocker=snapshot["blocker"])
            return snapshot
        finally:
            context.close()


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only local LinkedIn message capture proof")
    parser.add_argument("--limit-threads", type=int, default=3, help="Maximum visible message threads to capture")
    parser.add_argument("--headed", action="store_true", help="Run browser headed so Tom can log in/observe")
    parser.add_argument("--write", action="store_true", help="Write JSON and markdown outputs")
    parser.add_argument("--json-out", default=str(DEFAULT_JSON_OUT), help="Snapshot JSON output path")
    parser.add_argument("--md-out", default=str(DEFAULT_MD_OUT), help="Human markdown output path")
    parser.add_argument("--state-out", default=str(DEFAULT_STATE_OUT), help="Capture continuity/retry state output path")
    parser.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR), help="Persistent browser profile path outside workspace")
    parser.add_argument("--browser", choices=["chromium", "firefox", "webkit"], default="chromium")
    parser.add_argument("--timeout-ms", type=int, default=45000)
    parser.add_argument("--settle-ms", type=int, default=5000)
    parser.add_argument("--retry-attempts", type=int, default=2, help="Visible-thread extraction attempts before failing closed")
    parser.add_argument("--diagnostic", action="store_true", help="Force diagnostic mode for this pass")
    parser.add_argument("--login-wait-seconds", type=int, default=180, help="When headed and login is required, wait this long for manual login")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if args.limit_threads < 1 or args.limit_threads > 10:
        print("--limit-threads must be between 1 and 10", file=sys.stderr)
        return 2
    snapshot = run_capture(args)
    if args.write:
        write_outputs(snapshot, Path(args.json_out), Path(args.md_out))
        write_capture_state(Path(args.state_out), snapshot)
    else:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    state = snapshot.get("coverage_state")
    return 0 if state in {"complete", "coverage_incomplete", "login_required", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
