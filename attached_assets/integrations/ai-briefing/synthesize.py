#!/usr/bin/env python3
"""
AI Briefing Synthesizer — OpenClaw Integration
===============================================

Takes the ranked shortlist, optionally enriches top items via Tavily,
generates the finished briefing using Claude Sonnet, and writes both the
dated archive file and AI_BRIEFING_CURRENT.md.

Falls back to a structured markdown briefing from the shortlist if Sonnet fails.
Sends an optional Telegram ready-notification after file write.

Input:
  ~/.openclaw/ai-briefing/ranked/YYYY-MM-DD.json  (from rank.py)
  ~/.openclaw/ai-briefing/included-items.json      (updated after synthesis)

Output:
  ~/.openclaw/ai-briefing/briefings/AI_BRIEFING_YYYY-MM-DD.md
  ~/.openclaw/ai-briefing/AI_BRIEFING_CURRENT.md   (canonical L1 handoff)
  ~/.openclaw/ai-briefing/included-items.json       (updated)
  ~/.openclaw/ai-briefing/state.json               (updated)

Usage:
  python3 synthesize.py [--ranked-file path] [--no-telegram] [--no-tavily]
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

STATE_DIR       = Path.home() / ".openclaw"
BRIEFING_DIR    = STATE_DIR / "ai-briefing"
RANKED_DIR      = BRIEFING_DIR / "ranked"
BRIEFINGS_DIR   = BRIEFING_DIR / "briefings"
CURRENT_FILE    = BRIEFING_DIR / "AI_BRIEFING_CURRENT.md"
INCLUDED_FILE   = BRIEFING_DIR / "included-items.json"
STATE_FILE      = BRIEFING_DIR / "state.json"
TAVILY_SCRIPT   = Path.home() / ".openclaw" / "integrations" / "tavily" / "search.py"

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
SONNET_MODEL      = "claude-sonnet-4-5"

TAVILY_MAX_ITEMS    = 4     # enrich at most this many items
TAVILY_MAX_CHARS    = 3000  # max content chars per Tavily result
TAVILY_TIMEOUT      = 25    # seconds

LOG_PREFIX = "[ai-briefing/synthesize]"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[{ts()}] {LOG_PREFIX} {msg}", flush=True)


def log_err(msg: str) -> None:
    print(f"[{ts()}] {LOG_PREFIX} ERROR: {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# .env / config
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    env_file = STATE_DIR / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv()


def _cfg(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


# ---------------------------------------------------------------------------
# State / JSON helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path, default) -> dict | list:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception as e:
        log_err(f"Could not read {path}: {e} — using default")
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        tmp.replace(path)
    except Exception as e:
        log_err(f"Could not write {path}: {e}")


def load_state() -> dict:
    return _load_json(STATE_FILE, {})


def save_state(state: dict) -> None:
    _write_json(STATE_FILE, state)


# ---------------------------------------------------------------------------
# Load ranked shortlist
# ---------------------------------------------------------------------------

def load_ranked(ranked_file: Path) -> dict:
    data = _load_json(ranked_file, {})
    if not isinstance(data, dict):
        return {}
    return data


# ---------------------------------------------------------------------------
# Tavily enrichment
# ---------------------------------------------------------------------------

def _tavily_fetch(url: str) -> str | None:
    """
    Use the Tavily search.py script to fetch full article content for a URL.
    Passes --raw-json so we receive untruncated result content and apply
    TAVILY_MAX_CHARS ourselves rather than relying on the 500-char CLI format.
    Returns content string (capped at TAVILY_MAX_CHARS) or None on failure/timeout.
    """
    import subprocess

    tavily_key = _cfg("TAVILY_API_KEY")
    if not tavily_key:
        return None

    if not TAVILY_SCRIPT.exists():
        return None

    try:
        result = subprocess.run(
            ["python3", str(TAVILY_SCRIPT), url,
             "--search-depth", "advanced", "--max-results", "1",
             "--include-answer", "--raw-json"],
            capture_output=True, text=True, timeout=TAVILY_TIMEOUT,
        )
        if result.returncode != 0:
            return None
        raw = result.stdout.strip()
        if not raw:
            return None
        # Parse raw JSON and concatenate available content fields
        data = json.loads(raw)
        parts: list[str] = []
        if data.get("answer"):
            parts.append(data["answer"])
        for r in data.get("results", []):
            content = r.get("content", "").strip()
            if content:
                parts.append(content)
        combined = "\n\n".join(parts).strip()
        if not combined:
            return None
        return combined[:TAVILY_MAX_CHARS]
    except subprocess.TimeoutExpired:
        log(f"Tavily timeout for {url[:60]}")
        return None
    except (json.JSONDecodeError, KeyError) as e:
        log_err(f"Tavily JSON parse error: {e}")
        return None
    except Exception as e:
        log_err(f"Tavily fetch error: {e}")
        return None


def enrich_with_tavily(shortlist: list[dict], use_tavily: bool) -> tuple[list[dict], int]:
    """Fetch full content for Tavily-eligible items. Returns (shortlist, enriched_count)."""
    if not use_tavily:
        return shortlist, 0

    enriched_count = 0
    for item in shortlist[:TAVILY_MAX_ITEMS]:
        if not item.get("tavily_eligible", False):
            continue
        url = item.get("url", "")
        if not url:
            continue
        log(f"Tavily: fetching {item.get('title','')[:60]}…")
        content = _tavily_fetch(url)
        if content:
            item["tavily_content"] = content
            enriched_count += 1
            log(f"  Enriched: {len(content)} chars")
        else:
            log(f"  Tavily unavailable — using title + snippet for this item")

    log(f"Tavily enrichment: {enriched_count}/{min(len(shortlist), TAVILY_MAX_ITEMS)} items enriched")
    return shortlist, enriched_count


# ---------------------------------------------------------------------------
# Sonnet synthesis
# ---------------------------------------------------------------------------

def _build_synthesis_prompt(shortlist: list[dict], quiet_week: bool, watch_items: list[dict]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")

    if quiet_week:
        # Quiet week: always suppress shortlist items from the synthesis prompt.
        # Any borderline items (shortlist with 1 qualified item) are treated as
        # watch items so the output contract is consistent.
        items_text = "(No items met the relevance threshold this week.)"
        watch_items = list((shortlist + list(watch_items))[:3])  # merge, cap at 3 for quiet weeks
    else:
        parts = []
        for i, item in enumerate(shortlist, 1):
            part = (
                f"ITEM {i}\n"
                f"Title: {item.get('title', '')}\n"
                f"Source: {item.get('source_name', '')} ({item.get('source_url', '')})\n"
                f"Published: {item.get('published', '')}\n"
                f"Score: {item.get('haiku_score', 0)}/20 — {item.get('haiku_reason', '')}\n"
                f"Category: {', '.join(item.get('source_category', ['general']))}\n"
            )
            if "tavily_content" in item:
                part += f"Full content:\n{item['tavily_content']}\n"
            else:
                part += f"Summary: {item.get('summary', '')}\n"
            parts.append(part)
        items_text = "\n\n---\n\n".join(parts)

    watch_text = ""
    if watch_items:
        watch_text = "\n\nWATCH ITEMS (borderline — note but don't deep-dive):\n"
        for w in watch_items:
            watch_text += f"• {w.get('title','')} — {w.get('source_name','')} ({w.get('published','')})\n"

    prompt = f"""You are writing the weekly AI briefing for Tom Dean, an independent AI consultant who advises enterprise clients.

Tom's briefing standard: every included item must change how he advises clients, spots opportunities, or thinks about the field. Do not fill space with low-value content.

Today: {today}

FORMAT — use exactly this structure for each included item:

### [n]. <Title>
**Source:** <publication> · <date>
**Category:** <model-capability | enterprise-adoption | agent-tooling | economics | governance | risk>
**What changed:** <1–2 sentences — the news itself, factually>
**Why it matters:** <1–2 sentences — consulting implication>
**What to think or say differently:**
- <concrete bullet>
- <concrete bullet>
- <concrete bullet if warranted>

If this is a quiet week with nothing materially important, write:
> Nothing materially important this week.
Then list any watch items as a brief bullet list under "## Watch Items".

ITEMS TO SYNTHESISE:
{items_text}
{watch_text}

Write the briefing body now. Start directly with the first item (or the quiet week statement). No preamble."""

    return prompt


def _call_sonnet(prompt: str, api_key: str) -> str | None:
    """Call Claude Sonnet. Returns generated text or None on failure."""
    payload = json.dumps({
        "model": SONNET_MODEL,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
        return result["content"][0]["text"].strip()
    except urllib.error.HTTPError as e:
        log_err(f"Sonnet HTTP error {e.code}: {e.read().decode()[:200]}")
        return None
    except Exception as e:
        log_err(f"Sonnet API error: {e}")
        return None


def build_fallback_briefing(shortlist: list[dict], quiet_week: bool, watch_items: list[dict]) -> str:
    """
    Structured markdown fallback when Sonnet is unavailable.
    Always produces a valid briefing file.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    lines = []

    if quiet_week:
        # Quiet week: suppress shortlist items from the briefing body.
        # Merge them into watch items so output contract is consistent.
        watch_items = (shortlist + list(watch_items))[:3]
        lines.append("> Nothing materially important this week.")
        lines.append("")
    else:
        for i, item in enumerate(shortlist, 1):
            cats = item.get("source_category", ["general"])
            cat_str = cats[0] if cats else "general"
            lines.append(f"### {i}. {item.get('title', '(no title)')}")
            lines.append(f"**Source:** {item.get('source_name', '')} · {item.get('published', '')[:10]}")
            lines.append(f"**Category:** {cat_str}")
            lines.append(f"**What changed:** {item.get('summary', '(no summary available)')[:400]}")
            lines.append(f"**Why it matters:** _(Sonnet synthesis unavailable — see source for full analysis)_")
            lines.append(f"**Source URL:** {item.get('url', '')}")
            lines.append("")

    if watch_items:
        lines.append("## Watch Items")
        lines.append("")
        for w in watch_items:
            lines.append(f"- **{w.get('title', '')}** — {w.get('source_name', '')} ({w.get('published', '')[:10]})")
            lines.append(f"  {w.get('url', '')}")
        lines.append("")

    lines.append("---")
    lines.append("_⚠️ This briefing was generated by the structured fallback (Claude Sonnet was unavailable)._")
    lines.append("_Content is unprocessed feed data — synthesis and consulting framing not applied._")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Build the full briefing document
# ---------------------------------------------------------------------------

def build_briefing_document(
    body: str,
    shortlist: list[dict],
    quiet_week: bool,
    period_start: str,
    sources_count: int,
    items_total_fetched: int,
    items_new: int,
    items_shortlisted: int,
    items_included: int,
    fallback_used: bool,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    today = datetime.now().strftime("%Y-%m-%d")

    header = f"""# AI Briefing — {today}

| Field | Value |
|-------|-------|
| Generated | {now} |
| Period covered | {period_start} → {today} |
| Sources polled | {sources_count} |
| Items fetched (total) | {items_total_fetched} |
| Items new (deduped) | {items_new} |
| Items shortlisted | {items_shortlisted} |
| Items included | {items_included} |
| Synthesis | {'⚠️ Fallback (Sonnet unavailable)' if fallback_used else '✅ Claude Sonnet'} |

---

"""
    return header + body.strip() + "\n"


# ---------------------------------------------------------------------------
# Write briefing files
# ---------------------------------------------------------------------------

def write_briefing(content: str) -> tuple[Path, Path]:
    today = datetime.now().strftime("%Y-%m-%d")
    dated_file = BRIEFINGS_DIR / f"AI_BRIEFING_{today}.md"

    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    dated_file.write_text(content, encoding="utf-8")
    log(f"Wrote dated briefing: {dated_file}")

    CURRENT_FILE.write_text(content, encoding="utf-8")
    log(f"Updated AI_BRIEFING_CURRENT.md")

    return dated_file, CURRENT_FILE


# ---------------------------------------------------------------------------
# Update included-items.json
# ---------------------------------------------------------------------------

def _title_tokens(title: str) -> list[str]:
    """Return significant words from a title for cross-run topic fingerprinting."""
    import re as _re
    stopwords = {"the", "a", "an", "and", "or", "in", "on", "for", "of",
                 "to", "with", "from", "is", "are", "as", "it", "its",
                 "how", "why", "what", "by", "at", "be", "this", "that", "has"}
    words = _re.findall(r"[a-z]{3,}", title.lower())
    return [w for w in words if w not in stopwords]


def update_included(shortlist: list[dict]) -> None:
    included = _load_json(INCLUDED_FILE, {})
    if not isinstance(included, dict):
        included = {}

    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now().strftime("%Y-%m-%d")
    for item in shortlist:
        key = item.get("url_hash") or item.get("url", "")
        if key:
            included[key] = {
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "title_tokens": _title_tokens(item.get("title", "")),
                "source": item.get("source_name", ""),
                "included_at": now,
                "briefing_date": today,
            }

    _write_json(INCLUDED_FILE, included)
    log(f"included-items.json updated ({len(included)} total entries)")


# ---------------------------------------------------------------------------
# Telegram notification
# ---------------------------------------------------------------------------

def send_telegram_ready(dated_file: Path, items_included: int, quiet_week: bool) -> None:
    token = _cfg("TELEGRAM_BOT_TOKEN")
    chat_id = _cfg("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        log("No Telegram credentials — skipping notification")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    if quiet_week:
        msg = f"📰 *AI Briefing ready* — {today}\n_Quiet week: nothing materially important._\nSend `/ai-briefing` to read."
    else:
        msg = f"📰 *AI Briefing ready* — {today}\n_{items_included} item(s) this week._\nSend `/ai-briefing` to read."

    payload = json.dumps({
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown",
    }).encode()

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            log("Telegram ready-notification sent")
    except Exception as e:
        log_err(f"Telegram notification failed (non-fatal): {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def synthesize(ranked_file: Path, use_tavily: bool, send_notification: bool) -> dict:
    run_start = datetime.now(timezone.utc).isoformat()

    ranked_data = load_ranked(ranked_file)
    if not ranked_data:
        log_err(f"Could not load ranked data from {ranked_file}")
        return {"run_start": run_start, "error": "no ranked data"}

    shortlist    = ranked_data.get("shortlist", [])
    watch_items  = ranked_data.get("watch_items", [])
    quiet_week   = ranked_data.get("quiet_week", True)
    source_raw   = ranked_data.get("source_raw", "")

    log(f"Shortlist: {len(shortlist)} items, quiet_week={quiet_week}")

    # Load collection stats from state
    state = load_state()
    collect_stats = state.get("collect", {})
    rank_stats    = state.get("rank", {})

    sources_count       = collect_stats.get("sources_ok", 0)
    items_total_fetched = collect_stats.get("items_total_fetched", 0)
    items_new           = collect_stats.get("items_new", 0)
    items_shortlisted   = rank_stats.get("items_shortlisted", len(shortlist))

    # Determine period covered: use last_briefing_date from state (the boundary
    # of the previous briefing) so the header accurately reflects the interval.
    # Falls back to last Monday if state has no record.
    last_briefing_date = state.get("last_briefing_date", "")
    if last_briefing_date:
        period_start = last_briefing_date
    else:
        from datetime import timedelta
        today = datetime.now()
        days_since_monday = today.weekday()  # 0 = Monday
        last_monday = today - timedelta(days=days_since_monday + 7)
        period_start = last_monday.strftime("%Y-%m-%d")

    # Tavily enrichment
    tavily_enriched_count = 0
    if shortlist and use_tavily:
        shortlist, tavily_enriched_count = enrich_with_tavily(shortlist, use_tavily)

    # Synthesis
    api_key = _cfg("ANTHROPIC_API_KEY")
    fallback_used = False
    body = None

    if api_key:
        log(f"Calling Claude Sonnet for synthesis…")
        prompt = _build_synthesis_prompt(shortlist, quiet_week, watch_items)
        body = _call_sonnet(prompt, api_key)

    if body is None:
        if api_key:
            log_err("Sonnet synthesis failed — using structured fallback")
        else:
            log("No ANTHROPIC_API_KEY — using structured fallback briefing")
        body = build_fallback_briefing(shortlist, quiet_week, watch_items)
        fallback_used = True

    # Compute rendered item set first so items_included is consistent everywhere.
    # - Non-quiet week: shortlist items (rendered as main briefing entries)
    # - Quiet week: merged watch list rendered under "Watch Items" in the doc
    #   (shortlist borderline items are merged in, capped at 3)
    # items_included reflects what actually appeared in the document.
    if quiet_week:
        rendered = (shortlist + [w for w in watch_items if w not in shortlist])[:3]
        items_included = len(rendered)   # watch items are the rendered items
    else:
        rendered = shortlist
        items_included = len(rendered)

    # Build full document with header
    content = build_briefing_document(
        body=body,
        shortlist=shortlist,
        quiet_week=quiet_week,
        period_start=period_start,
        sources_count=sources_count,
        items_total_fetched=items_total_fetched,
        items_new=items_new,
        items_shortlisted=items_shortlisted,
        items_included=items_included,
        fallback_used=fallback_used,
    )

    # Write files (primary completion condition)
    dated_file, current_file = write_briefing(content)

    # Record deterministically rendered items so they don't resurface
    if rendered:
        update_included(rendered)

    # Send notification (optional, non-blocking)
    if send_notification:
        send_telegram_ready(dated_file, items_included, quiet_week)

    summary = {
        "run_start": run_start,
        "ranked_file": str(ranked_file),
        "briefing_file": str(dated_file),
        "current_file": str(current_file),
        "items_included": items_included,
        "quiet_week": quiet_week,
        "fallback_used": fallback_used,
        "tavily_used": tavily_enriched_count > 0,
        "tavily_enriched_count": tavily_enriched_count,
        "notification_sent": send_notification,
    }

    return summary


def find_latest_ranked_file() -> Path | None:
    if not RANKED_DIR.exists():
        return None
    files = sorted(RANKED_DIR.glob("*.json"), reverse=True)
    return files[0] if files else None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AI Briefing Synthesizer")
    p.add_argument("--ranked-file", type=Path, default=None,
                   help="Path to ranked items JSON (default: latest in ranked/)")
    p.add_argument("--no-telegram", action="store_true",
                   help="Skip Telegram notification")
    p.add_argument("--no-tavily", action="store_true",
                   help="Skip Tavily article enrichment")
    return p.parse_args()


def main() -> dict:
    args = parse_args()

    ranked_file = args.ranked_file
    if ranked_file is None:
        ranked_file = find_latest_ranked_file()
    if ranked_file is None or not ranked_file.exists():
        log_err("No ranked file found. Run rank.py first.")
        sys.exit(1)

    log(f"Synthesizing from {ranked_file}")
    summary = synthesize(
        ranked_file=ranked_file,
        use_tavily=not args.no_tavily,
        send_notification=not args.no_telegram,
    )

    state = load_state()
    state["synthesize"] = summary

    # Only advance last_briefing_date / last_successful_run when synthesis
    # actually produced a valid briefing file (no error key, non-empty path).
    briefing_file = summary.get("briefing_file", "")
    has_error = "error" in summary
    if briefing_file and briefing_file != "unknown" and not has_error:
        state["last_successful_run"] = datetime.now(timezone.utc).isoformat()
        state["last_briefing_date"] = datetime.now().strftime("%Y-%m-%d")

    save_state(state)

    if has_error:
        log_err(f"Synthesis error: {summary['error']}")
        sys.exit(1)

    log(f"Synthesis complete: {briefing_file}")
    return summary


if __name__ == "__main__":
    main()
