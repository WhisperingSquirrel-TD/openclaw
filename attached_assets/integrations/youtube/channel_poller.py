#!/usr/bin/env python3
"""
YouTube Channel Poller — OpenClaw Integration
==============================================

WHAT THIS DOES
--------------
Polls one or more YouTube channels for new videos via their public RSS feeds.
For each new video it:
  1. Fetches the transcript/captions (via youtube-transcript-api, no API key)
  2. Generates a useful summary and key takeaways via the Anthropic API
     (falls back to raw-transcript-only if no API key is configured)
  3. Writes a formatted Markdown resource file to the transcripts directory
  4. Sends a Telegram notification with title + slug

TRANSCRIPT DIRECTORY
--------------------
  ~/.openclaw/workspace/reference/transcripts/

FILENAME FORMAT
---------------
  YYYY-MM-DD - <short-slug>.md
  e.g. 2026-04-15 - john-cropper-pyramid-learning.md

FILE STRUCTURE
--------------
  # <Title>
  - Received: YYYY-MM-DD HH:MM Europe/London
  - Source: <YouTube URL>
  - Topic: <short topic from title>
  - Status: resource

  ## Useful Summary
  - bullets

  ## Key Takeaways
  - reusable points

  ## Raw Transcript
  <full transcript text>

CHANNEL CONFIG
--------------
  ~/.openclaw/integrations/youtube/channels.json
  [
    {"channel_id": "UCxxxxxx", "label": "Optional friendly name"},
    {"channel_url": "https://www.youtube.com/@ChannelName", "label": "Another channel"}
  ]

  Supported fields per entry (one of channel_id or channel_url required):
    channel_id   — YouTube channel ID (starts with UC...)
    channel_url  — YouTube channel URL (@handle, /c/name, /user/name, or channel/UC...)
    label        — optional friendly name for Telegram notifications
    active       — set to false to pause without deleting (default: true)

REQUIRED ENV VARS
-----------------
  None strictly required — transcript fetch needs no API key.

OPTIONAL ENV VARS
-----------------
  ANTHROPIC_API_KEY    — enables AI summary generation (Claude Haiku, cheapest)
  OPENAI_API_KEY       — fallback AI provider if Anthropic key not present
  OPENCLAW_AI_MODEL    — override AI model for summaries (default: claude-haiku-4-5)
  TELEGRAM_BOT_TOKEN   — for new-video notifications
  TELEGRAM_CHAT_ID     — for new-video notifications
  YOUTUBE_POLL_LANGS   — comma-separated preferred caption languages (default: en)

CRON
----
  Installed by install-forked-openclaw.sh:
  */30 * * * * python3 ~/.openclaw/integrations/youtube/channel_poller.py \
                >> ~/.openclaw/integrations/youtube/channel-poller.log 2>&1

MANUAL TEST
-----------
  python3 ~/.openclaw/integrations/youtube/channel_poller.py
  python3 ~/.openclaw/integrations/youtube/channel_poller.py --video <url_or_id>
"""

import argparse
import fcntl
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

STATE_DIR     = Path.home() / ".openclaw"
INTEGRATIONS  = STATE_DIR / "integrations" / "youtube"
CHANNELS_FILE = INTEGRATIONS / "channels.json"
STATE_FILE    = INTEGRATIONS / "channel-poller-state.json"
LOCK_FILE     = Path("/tmp/openclaw-youtube-channel-poller.lock")
LOG_PREFIX    = "[youtube-channel-poller]"
TRANSCRIPTS_DIR = STATE_DIR / "workspace" / "reference" / "transcripts"

# How far back to look for videos on first run (days)
INITIAL_LOOKBACK_DAYS = 3
# Max videos to process per channel per run (avoids a flood on first setup)
MAX_PER_CHANNEL = 5
# Summary model preference
DEFAULT_AI_MODEL         = "claude-haiku-4-5"
ANTHROPIC_API_URL        = "https://api.anthropic.com/v1/messages"
ANTHROPIC_BATCH_URL      = "https://api.anthropic.com/v1/messages/batches"
OPENAI_API_URL           = "https://api.openai.com/v1/chat/completions"
# Batches older than this are considered expired — drop them
BATCH_MAX_AGE_HOURS      = 23

RSS_NS = "http://www.w3.org/2005/Atom"
YT_NS  = "http://www.youtube.com/xml/schemas/2015"
MEDIA_NS = "http://search.yahoo.com/mrss/"


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    env_file = STATE_DIR / ".env"
    if not env_file.exists():
        return
    try:
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
    except Exception:
        pass


_load_dotenv()


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
# Lock
# ---------------------------------------------------------------------------

def acquire_lock() -> object:
    fh = open(LOCK_FILE, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fh
    except OSError:
        print(f"{LOG_PREFIX} Another instance already running. Exiting.", file=sys.stderr)
        sys.exit(0)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def load_state() -> dict:
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            data.setdefault("pending_video_ids", [])
            data.setdefault("pending_batches", [])
            return data
    except Exception as e:
        log(f"WARNING: Could not read state: {e} — starting fresh")
    return {"processed_ids": [], "pending_video_ids": [], "pending_batches": [], "last_run": None}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(state, indent=2))
        tmp.replace(STATE_FILE)
    except Exception as e:
        log_err(f"Could not save state: {e}")


# ---------------------------------------------------------------------------
# Channel config
# ---------------------------------------------------------------------------

def load_channels() -> list[dict]:
    if not CHANNELS_FILE.exists():
        log("No channels.json found — creating empty template")
        CHANNELS_FILE.parent.mkdir(parents=True, exist_ok=True)
        CHANNELS_FILE.write_text(json.dumps([
            {"_comment": "Add channels to watch. Remove this line. Example:"},
            {"channel_id": "UC_x5XG1OV2P6uZZ5FSM9Ttw", "label": "YouTube Developers"},
        ], indent=2))
        return []

    try:
        channels = json.loads(CHANNELS_FILE.read_text())
    except Exception as e:
        log_err(f"Could not parse channels.json: {e}")
        return []

    active = []
    for ch in channels:
        if "_comment" in ch:
            continue
        if not ch.get("active", True):
            continue
        if not (ch.get("channel_id") or ch.get("channel_url")):
            log(f"WARNING: Channel entry missing channel_id/channel_url — skipping: {ch}")
            continue
        active.append(ch)
    return active


def _resolve_handle_to_channel_id(handle_or_url: str) -> str:
    """
    Fetch a YouTube @handle or channel page and extract the UC... channel ID.
    YouTube embeds channelId in its page JSON — no API key needed.
    Returns '' if resolution fails.
    """
    handle_m = re.search(r'youtube\.com/@([\w.-]+)', handle_or_url)
    if handle_m:
        fetch_url = f"https://www.youtube.com/@{handle_m.group(1)}"
    elif handle_or_url.startswith("http"):
        fetch_url = handle_or_url.split("?")[0]
    else:
        return ""

    try:
        req = urllib.request.Request(
            fetch_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log_err(f"Handle resolution fetch failed for {fetch_url}: {e}")
        return ""

    patterns = [
        r'"channelId"\s*:\s*"(UC[\w-]{22})"',
        r'"externalChannelId"\s*:\s*"(UC[\w-]{22})"',
        r'"key"\s*:\s*"channelId"\s*,\s*"value"\s*:\s*"(UC[\w-]{22})"',
        r'channel_id=(UC[\w-]{22})',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return ""


def resolve_channel_id(ch: dict) -> str | None:
    """
    Return the channel ID for a channel entry.
    For @handle URLs, fetches the channel page to extract the UC... ID.
    Returns None only if we truly cannot determine the ID.
    """
    if ch.get("channel_id"):
        return ch["channel_id"].strip()

    url = (ch.get("channel_url") or "").strip().rstrip("/")

    # Direct UC... ID embedded in a /channel/ URL
    m = re.search(r'/channel/(UC[\w-]+)', url)
    if m:
        return m.group(1)

    # @handle — resolve by fetching the page
    if "/@" in url or re.search(r'/(?:c|user)/', url):
        resolved = _resolve_handle_to_channel_id(url)
        if resolved:
            log(f"  Resolved handle to channel_id: {resolved} (from {url})")
            return resolved
        log(f"  WARNING: Could not resolve channel_id for {url} — RSS may not work")

    return None


def rss_url_for_channel(ch: dict) -> str:
    """
    Return the YouTube RSS feed URL for a channel entry.
    Always prefers the ?channel_id= form (most reliable).
    Falls back to ?user= for legacy entries only.
    """
    channel_id = resolve_channel_id(ch)
    if channel_id:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    # Last-resort legacy fallback for old /user/ style channels
    url = (ch.get("channel_url") or "").strip().rstrip("/")
    m = re.search(r'/user/([\w.-]+)', url)
    if m:
        log(f"  WARNING: Using deprecated ?user= RSS endpoint for {url}")
        return f"https://www.youtube.com/feeds/videos.xml?user={m.group(1)}"

    log_err(f"Cannot build RSS URL for channel: {ch}")
    return ""


# ---------------------------------------------------------------------------
# RSS fetching
# ---------------------------------------------------------------------------

def fetch_rss(rss_url: str) -> list[dict]:
    """Fetch and parse YouTube RSS feed. Returns list of video dicts."""
    try:
        req = urllib.request.Request(rss_url, headers={"User-Agent": "OpenClaw-YouTubePoller/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        log_err(f"HTTP {e.code} fetching RSS {rss_url}")
        return []
    except Exception as e:
        log_err(f"Error fetching RSS {rss_url}: {e}")
        return []

    try:
        root = ET.fromstring(raw)
    except Exception as e:
        log_err(f"XML parse error for {rss_url}: {e}")
        return []

    videos = []
    for entry in root.findall(f"{{{RSS_NS}}}entry"):
        def _find(tag, ns=RSS_NS):
            el = entry.find(f"{{{ns}}}{tag}")
            return el.text.strip() if el is not None and el.text else ""

        video_id_el = entry.find(f"{{{YT_NS}}}videoId")
        video_id = video_id_el.text.strip() if video_id_el is not None and video_id_el.text else ""

        channel_id_el = entry.find(f"{{{YT_NS}}}channelId")
        channel_id = channel_id_el.text.strip() if channel_id_el is not None and channel_id_el.text else ""

        title = _find("title")
        published = _find("published")
        link_el = entry.find(f"{{{RSS_NS}}}link")
        url = link_el.attrib.get("href", "") if link_el is not None else f"https://www.youtube.com/watch?v={video_id}"

        if not video_id:
            continue

        videos.append({
            "video_id":  video_id,
            "channel_id": channel_id,
            "title":     title,
            "published": published,
            "url":       url or f"https://www.youtube.com/watch?v={video_id}",
        })

    return videos


# ---------------------------------------------------------------------------
# Transcript fetch (via youtube-transcript-api)
# ---------------------------------------------------------------------------

def fetch_transcript(video_id: str) -> tuple[str, str]:
    """
    Returns (transcript_text, source_info).
    transcript_text is empty string if no transcript available.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        log_err("youtube-transcript-api not installed — cannot fetch transcript")
        log_err("Fix: pip3 install --break-system-packages youtube-transcript-api")
        return "", "library not installed"

    langs = [l.strip() for l in os.environ.get("YOUTUBE_POLL_LANGS", "en").split(",") if l.strip()]

    if not hasattr(YouTubeTranscriptApi, "list_transcripts"):
        log_err(
            "youtube-transcript-api is too old — list_transcripts missing. "
            "Fix: pip3 install --break-system-packages --upgrade youtube-transcript-api"
        )
        return "", "library version too old — upgrade youtube-transcript-api"

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    except Exception as e:
        err_str = str(e).lower()
        if "no transcripts" in err_str or "could not retrieve" in err_str:
            return "", "no captions available"
        if "unavailable" in err_str or "private" in err_str:
            return "", "video unavailable or private"
        return "", f"error: {e}"

    transcript = None
    source_info = ""

    for getter in [
        lambda: transcript_list.find_transcript(langs),
        lambda: transcript_list.find_generated_transcript(langs),
        lambda: next(iter(transcript_list), None),
    ]:
        try:
            t = getter()
            if t:
                transcript = t.fetch()
                source_info = f"{'auto-generated' if t.is_generated else 'manual'} ({t.language_code})"
                break
        except Exception:
            continue

    if not transcript:
        return "", "fetch failed"

    parts = []
    for entry in transcript:
        text = (entry.get("text") or "").strip()
        if text:
            parts.append(text)

    return " ".join(parts), source_info


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------

def make_slug(title: str, max_len: int = 50) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:max_len].rstrip("-")


# ---------------------------------------------------------------------------
# AI summary — shared prompt builder + response parser
# ---------------------------------------------------------------------------

def _build_summary_prompt(title: str, transcript: str) -> str:
    preview = transcript[:6000]
    if len(transcript) > 6000:
        preview += " [...transcript truncated for summary...]"
    return (
        f"You are summarising a YouTube video transcript for a personal knowledge base.\n\n"
        f"Video title: {title}\n\n"
        f"Transcript:\n{preview}\n\n"
        f"Produce two sections:\n"
        f"1. USEFUL SUMMARY: 4-6 bullet points covering what the video is actually about — "
        f"specific enough to jog memory, not generic.\n"
        f"2. KEY TAKEAWAYS: 3-5 reusable, actionable points someone could apply. "
        f"If the content is not actionable, list the most memorable ideas instead.\n\n"
        f"Format your response EXACTLY as:\n"
        f"SUMMARY:\n- bullet\n- bullet\n\n"
        f"TAKEAWAYS:\n- bullet\n- bullet\n\n"
        f"Be specific and concrete. No preamble, no explanation, just the two sections."
    )


def _parse_summary_response(raw: str) -> tuple[str, str]:
    summary_lines: list[str] = []
    takeaway_lines: list[str] = []
    current = None
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("SUMMARY"):
            current = "summary"
            continue
        if stripped.upper().startswith("TAKEAWAY"):
            current = "takeaways"
            continue
        if stripped.startswith("-") and current == "summary":
            summary_lines.append(stripped)
        elif stripped.startswith("-") and current == "takeaways":
            takeaway_lines.append(stripped)
    return (
        "\n".join(summary_lines)  or "- See raw transcript below.",
        "\n".join(takeaway_lines) or "- See raw transcript below.",
    )


# ---------------------------------------------------------------------------
# AI summary — synchronous path (used for --sync / --video / OpenAI fallback)
# ---------------------------------------------------------------------------

def _call_anthropic_sync(prompt: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""
    model = os.environ.get("OPENCLAW_AI_MODEL", DEFAULT_AI_MODEL)
    payload = json.dumps({
        "model": model,
        "max_tokens": 800,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"].strip()
    except Exception as e:
        log_err(f"Anthropic API error: {e}")
        return ""


def _call_openai(prompt: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return ""
    model = os.environ.get("OPENCLAW_AI_MODEL", "gpt-4o-mini")
    payload = json.dumps({
        "model": model,
        "max_tokens": 800,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        OPENAI_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log_err(f"OpenAI API error: {e}")
        return ""


def generate_summary(title: str, transcript: str) -> tuple[str, str]:
    """
    Synchronous summary — used in --sync mode, --video mode, and OpenAI fallback.
    Returns (summary_bullets, takeaways_bullets).
    """
    if not transcript.strip():
        return "- No transcript available for this video.", "- No transcript available."

    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_openai    = bool(os.environ.get("OPENAI_API_KEY"))

    if not has_anthropic and not has_openai:
        return (
            "- AI summary not generated — no API key configured.\n"
            "  Add ANTHROPIC_API_KEY or OPENAI_API_KEY to ~/.openclaw/.env",
            "- Key takeaways not generated — no API key configured.",
        )

    prompt = _build_summary_prompt(title, transcript)
    raw = _call_anthropic_sync(prompt) if has_anthropic else _call_openai(prompt)

    if not raw:
        return (
            "- Summary generation failed — API call returned empty.",
            "- Takeaways generation failed — API call returned empty.",
        )
    return _parse_summary_response(raw)


# ---------------------------------------------------------------------------
# AI summary — Anthropic batch path (cron mode, 50% cost saving)
# ---------------------------------------------------------------------------

def _anthropic_headers() -> dict:
    return {
        "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


def submit_anthropic_batch(items: list[dict]) -> str | None:
    """
    Submit a Message Batch to Anthropic.
    items: list of {"custom_id": str, "title": str, "transcript": str}
    Returns the batch_id string on success, None on failure.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log_err("ANTHROPIC_API_KEY not set — cannot submit batch. Add it to ~/.openclaw/.env")
        return None

    model = os.environ.get("OPENCLAW_AI_MODEL", DEFAULT_AI_MODEL)
    requests_payload = []
    for item in items:
        requests_payload.append({
            "custom_id": item["custom_id"],
            "params": {
                "model": model,
                "max_tokens": 800,
                "messages": [{
                    "role": "user",
                    "content": _build_summary_prompt(item["title"], item["transcript"]),
                }],
            },
        })
    payload = json.dumps({"requests": requests_payload}).encode()
    req = urllib.request.Request(
        ANTHROPIC_BATCH_URL,
        data=payload,
        headers=_anthropic_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            batch_id = data.get("id", "")
            log(f"  Batch submitted: {batch_id} ({len(items)} requests)")
            return batch_id
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        log_err(f"Batch submit failed: HTTP {e.code} — {body}")
        return None
    except Exception as e:
        log_err(f"Batch submit failed: {e}")
        return None


def poll_anthropic_batch(batch_id: str) -> tuple[str, dict]:
    """
    Check batch status.
    Returns (processing_status, results_by_custom_id).
    processing_status is one of: in_progress | ended | canceling | canceled
    results_by_custom_id is populated only when status == 'ended'.
    """
    req = urllib.request.Request(
        f"{ANTHROPIC_BATCH_URL}/{batch_id}",
        headers=_anthropic_headers(),
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        log_err(f"Batch poll failed for {batch_id}: {e}")
        return "unknown", {}

    status = data.get("processing_status", "unknown")
    if status != "ended":
        counts = data.get("request_counts", {})
        log(f"  Batch {batch_id}: {status} — {counts}")
        return status, {}

    # Fetch results (newline-delimited JSON stream)
    results: dict[str, tuple[str, str]] = {}
    try:
        results_req = urllib.request.Request(
            f"{ANTHROPIC_BATCH_URL}/{batch_id}/results",
            headers=_anthropic_headers(),
        )
        with urllib.request.urlopen(results_req, timeout=30) as resp:
            for line in resp:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                custom_id = row.get("custom_id", "")
                result    = row.get("result", {})
                if result.get("type") == "succeeded":
                    text = result["message"]["content"][0]["text"].strip()
                    results[custom_id] = _parse_summary_response(text)
                else:
                    log(f"  Batch result {custom_id}: {result.get('type')} — using fallback")
                    results[custom_id] = (
                        "- Summary unavailable (batch error).",
                        "- Takeaways unavailable (batch error).",
                    )
    except Exception as e:
        log_err(f"Batch results fetch failed for {batch_id}: {e}")

    log(f"  Batch {batch_id} ended — {len(results)} result(s) retrieved")
    return "ended", results


def process_pending_batches(state: dict) -> int:
    """
    Check all pending batches. For each completed one, write files and notify.
    Returns the number of transcripts written.
    """
    pending = state.get("pending_batches", [])
    if not pending:
        return 0

    written = 0
    still_pending = []
    now = datetime.now(timezone.utc)

    for batch_entry in pending:
        batch_id     = batch_entry["batch_id"]
        submitted_at = batch_entry.get("submitted_at", "")
        videos       = batch_entry.get("videos", [])

        # Drop batches older than BATCH_MAX_AGE_HOURS — Anthropic expires them at 24h
        try:
            age_hours = (now - datetime.fromisoformat(submitted_at)).total_seconds() / 3600
        except Exception:
            age_hours = 0

        if age_hours > BATCH_MAX_AGE_HOURS:
            log(f"  Batch {batch_id} expired (age {age_hours:.1f}h) — dropping")
            # Release pending_video_ids so they could be re-attempted next run
            pending_ids = set(state.get("pending_video_ids", []))
            for v in videos:
                pending_ids.discard(v["video_id"])
            state["pending_video_ids"] = list(pending_ids)
            continue

        status, results = poll_anthropic_batch(batch_id)

        if status != "ended":
            still_pending.append(batch_entry)
            continue

        # Batch complete — write files and notify
        processed_ids  = set(state.get("processed_ids", []))
        pending_ids    = set(state.get("pending_video_ids", []))

        for v in videos:
            vid     = v["video_id"]
            title   = v.get("title", vid)
            summary, takeaways = results.get(v["custom_id"], (
                "- Summary unavailable.", "- Takeaways unavailable.",
            ))
            try:
                write_transcript_file(
                    video       = v,
                    transcript  = v.get("transcript", ""),
                    source_info = v.get("source_info", ""),
                    summary     = summary,
                    takeaways   = takeaways,
                )
                label = v.get("channel_label", "YouTube")
                slug  = (TRANSCRIPTS_DIR / "x").parent  # just need stem below
                # Re-derive filename stem the same way write_transcript_file does
                pub_raw = v.get("published", "")
                try:
                    dt = datetime.fromisoformat(pub_raw.replace("Z", "+00:00"))
                    date_str = dt.strftime("%Y-%m-%d")
                except Exception:
                    date_str = now.strftime("%Y-%m-%d")
                file_slug = f"{date_str} - {make_slug(title)}"
                notify(
                    f"📺 New transcript saved (batch)\n"
                    f"Channel: {label}\n"
                    f"Title: {title}\n"
                    f"File: {file_slug}\n"
                    f"Source: {v.get('url', '')}"
                )
                written += 1
            except Exception as e:
                log_err(f"  Failed writing batch result for {vid}: {e}")

            processed_ids.add(vid)
            pending_ids.discard(vid)

        state["processed_ids"]    = list(processed_ids)
        state["pending_video_ids"] = list(pending_ids)

    state["pending_batches"] = still_pending
    return written


# ---------------------------------------------------------------------------
# File writer
# ---------------------------------------------------------------------------

def _london_time(dt: datetime) -> str:
    """Format a UTC datetime as Europe/London (no pytz dependency — handles BST/GMT simply)."""
    # BST is UTC+1, last Sunday March to last Sunday October.
    # Simple approximation: if month is 4-10 inclusive, use UTC+1.
    offset = timedelta(hours=1) if 4 <= dt.month <= 10 else timedelta(hours=0)
    local = dt + offset
    tz_label = "BST" if offset.total_seconds() > 0 else "GMT"
    return local.strftime(f"%Y-%m-%d %H:%M") + f" {tz_label}"


def write_transcript_file(video: dict, transcript: str, source_info: str,
                           summary: str, takeaways: str) -> Path:
    """Write the formatted resource file. Returns the path written."""
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    title = video.get("title") or video.get("video_id", "untitled")
    slug  = make_slug(title)

    # Parse published date
    pub_raw = video.get("published", "")
    try:
        dt = datetime.fromisoformat(pub_raw.replace("Z", "+00:00"))
        date_str = dt.strftime("%Y-%m-%d")
        received_str = _london_time(dt.astimezone(timezone.utc).replace(tzinfo=None))
    except Exception:
        dt = datetime.now(timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
        received_str = _london_time(datetime.utcnow())

    filename = f"{date_str} - {slug}.md"
    path = TRANSCRIPTS_DIR / filename

    # Avoid overwriting if file already exists (e.g. duplicate slug)
    if path.exists():
        suffix = 2
        while path.exists():
            path = TRANSCRIPTS_DIR / f"{date_str} - {slug}-{suffix}.md"
            suffix += 1

    # Short topic from title (first 60 chars, cleaned)
    topic = re.sub(r'\s+', ' ', title).strip()[:60]

    url = video.get("url", f"https://www.youtube.com/watch?v={video['video_id']}")

    raw_section = transcript.strip() if transcript.strip() else "_No transcript available for this video._"

    # Derive a clear transcript status for the frontmatter
    if transcript.strip():
        transcript_status = f"full ({source_info})" if source_info else "full"
    else:
        transcript_status = f"unavailable — {source_info}" if source_info else "unavailable"

    content = (
        f"# {title}\n"
        f"- Received: {received_str} Europe/London\n"
        f"- Source: {url}\n"
        f"- Topic: {topic}\n"
        f"- Status: resource\n"
        f"- Transcript: {transcript_status}\n"
        f"\n"
        f"## Useful Summary\n"
        f"{summary}\n"
        f"\n"
        f"## Key Takeaways\n"
        f"{takeaways}\n"
        f"\n"
        f"## Raw Transcript\n"
        f"{raw_section}\n"
    )

    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    log(f"Wrote: {path.name}")
    return path


# ---------------------------------------------------------------------------
# Telegram notification
# ---------------------------------------------------------------------------

def _read_openclaw_config() -> dict:
    try:
        return json.loads((STATE_DIR / "openclaw.json").read_text())
    except Exception:
        return {}


def _get_telegram_creds() -> tuple[str, str]:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        return token, chat_id
    cfg = _read_openclaw_config()
    tg = cfg.get("channels", {}).get("telegram", {})
    if not token:
        token = tg.get("botToken", "")
        if not token:
            for acc in tg.get("accounts", {}).values():
                if isinstance(acc, dict) and acc.get("botToken"):
                    token = acc["botToken"]
                    break
    if not chat_id:
        allow_from = tg.get("allowFrom", [])
        if allow_from:
            chat_id = str(allow_from[0])
    return token, chat_id


def notify(msg: str) -> None:
    token, chat_id = _get_telegram_creds()
    if not token or not chat_id:
        return
    # Telegram hard limit is 4096 chars
    if len(msg) > 4096:
        msg = msg[:4090] + "\n…"
    try:
        payload = json.dumps({"chat_id": chat_id, "text": msg}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        log_err(f"Telegram notify failed: HTTP {e.code} — {body}")
    except Exception as e:
        log_err(f"Telegram notify failed: {e}")


# ---------------------------------------------------------------------------
# Process a single video — sync path (--sync / --video / OpenAI fallback)
# ---------------------------------------------------------------------------

def process_video_sync(video: dict, channel_label: str) -> bool:
    """Fetch transcript, generate summary synchronously, write file, notify."""
    vid   = video["video_id"]
    title = video.get("title", vid)

    log(f"Processing (sync): {title!r} ({vid})")

    transcript, source_info = fetch_transcript(vid)
    if not transcript:
        log(f"  No transcript ({source_info}) — saving stub file")

    summary, takeaways = generate_summary(title, transcript)
    path = write_transcript_file(video, transcript, source_info, summary, takeaways)

    label = channel_label or "YouTube"
    notify(
        f"📺 New transcript saved\n"
        f"Channel: {label}\n"
        f"Title: {title}\n"
        f"File: {path.stem}\n"
        f"Source: {video.get('url', '')}"
    )
    return True


# ---------------------------------------------------------------------------
# Main poll loop
# ---------------------------------------------------------------------------

def poll_channels(state: dict, sync: bool = False) -> int:
    """
    Poll all configured channels for new videos.

    sync=False (default, cron mode):
      Transcripts are fetched then the whole batch is submitted to the
      Anthropic Message Batches API (50% cheaper).  Files are written and
      Telegram notifications sent on the *next* run once the batch is done.
      Falls back to synchronous processing when only OpenAI is available.

    sync=True (--sync flag, used by /yt-run in mgmt-bot):
      Each video is processed immediately — transcript + summary + file write
      + Telegram notification all happen in this run.  More expensive but gives
      instant feedback when triggered manually from Telegram.
    """
    channels = load_channels()
    if not channels:
        log("No channels configured — nothing to poll")
        return 0

    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))

    # In batch mode we need Anthropic; OpenAI has no batch API so fall back to sync
    if not has_anthropic:
        sync = True

    processed_ids = set(state.get("processed_ids", []))
    pending_ids   = set(state.get("pending_video_ids", []))
    claimed_ids   = processed_ids | pending_ids  # don't re-process either set
    cutoff        = datetime.now(timezone.utc) - timedelta(days=INITIAL_LOOKBACK_DAYS)

    new_count    = 0
    batch_queue: list[dict] = []  # collected for batch submission (cron mode)

    for ch in channels:
        label = ch.get("label", ch.get("channel_id", ch.get("channel_url", "unknown")))
        rss   = rss_url_for_channel(ch)
        if not rss:
            continue

        log(f"Polling channel: {label}")
        videos = fetch_rss(rss)
        log(f"  RSS returned {len(videos)} video(s)")

        def _pub_dt(v):
            try:
                return datetime.fromisoformat(v["published"].replace("Z", "+00:00"))
            except Exception:
                return datetime.min.replace(tzinfo=timezone.utc)

        videos.sort(key=_pub_dt)

        channel_new = 0
        for video in videos:
            vid = video["video_id"]
            if vid in claimed_ids:
                continue

            pub_dt = _pub_dt(video)
            if pub_dt != datetime.min.replace(tzinfo=timezone.utc) and pub_dt < cutoff:
                processed_ids.add(vid)
                claimed_ids.add(vid)
                continue

            if channel_new >= MAX_PER_CHANNEL:
                log(f"  Hit MAX_PER_CHANNEL={MAX_PER_CHANNEL} — will catch remaining next run")
                break

            if sync:
                # ── Synchronous path (immediate result) ──────────────────
                try:
                    ok = process_video_sync(video, label)
                    if ok:
                        new_count += 1
                        channel_new += 1
                except Exception as e:
                    log_err(f"  Failed to process {vid}: {e}")
                processed_ids.add(vid)
                claimed_ids.add(vid)
                state["processed_ids"] = list(processed_ids)
                save_state(state)
                time.sleep(2)
            else:
                # ── Batch path — collect transcript, queue for submission ─
                title = video.get("title", vid)
                log(f"  Fetching transcript for batch: {title!r}")
                try:
                    transcript, source_info = fetch_transcript(vid)
                    batch_queue.append({
                        "custom_id":     f"vid_{vid}",
                        "video_id":      vid,
                        "title":         title,
                        "transcript":    transcript,
                        "source_info":   source_info,
                        "published":     video.get("published", ""),
                        "url":           video.get("url", f"https://www.youtube.com/watch?v={vid}"),
                        "channel_label": label,
                        # Pass through fields write_transcript_file needs
                        "channel_id":    video.get("channel_id", ""),
                    })
                    pending_ids.add(vid)
                    claimed_ids.add(vid)
                    channel_new += 1
                except Exception as e:
                    log_err(f"  Failed collecting {vid} for batch ({title!r}): {e} — skipping")
                    processed_ids.add(vid)
                    claimed_ids.add(vid)
                time.sleep(1)

        if channel_new == 0:
            log(f"  No new videos for {label}")

    # ── Submit batch (cron mode) ──────────────────────────────────────────
    if batch_queue:
        log(f"Submitting Anthropic batch for {len(batch_queue)} video(s)…")
        batch_id = submit_anthropic_batch(batch_queue)
        if batch_id:
            state.setdefault("pending_batches", []).append({
                "batch_id":     batch_id,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "videos":       batch_queue,
            })
            state["pending_video_ids"] = list(pending_ids)
            new_count = len(batch_queue)
            log(f"  Batch queued — transcripts will arrive on next poll run (~30 min)")
        else:
            # Batch submission failed — fall back to sync for this run
            log("  Batch submit failed — falling back to sync for these videos")
            for item in batch_queue:
                vid = item["video_id"]
                try:
                    video_meta = {
                        "video_id":  vid,
                        "title":     item["title"],
                        "published": item["published"],
                        "url":       item["url"],
                    }
                    summary, takeaways = generate_summary(item["title"], item["transcript"])
                    write_transcript_file(video_meta, item["transcript"],
                                          item["source_info"], summary, takeaways)
                    notify(
                        f"📺 New transcript saved (sync fallback)\n"
                        f"Channel: {item['channel_label']}\n"
                        f"Title: {item['title']}\n"
                        f"Source: {item['url']}"
                    )
                except Exception as e:
                    log_err(f"  Sync fallback failed for {vid}: {e}")
                processed_ids.add(vid)
                pending_ids.discard(vid)
            state["pending_video_ids"] = list(pending_ids)

    # Cap processed_ids to avoid unbounded growth (keep last 5000)
    ids_list = list(processed_ids)
    if len(ids_list) > 5000:
        ids_list = ids_list[-5000:]
    state["processed_ids"] = ids_list
    return new_count


# ---------------------------------------------------------------------------
# Single-video mode (--video flag) — always synchronous
# ---------------------------------------------------------------------------

def process_single_video_url(url_or_id: str) -> None:
    """Process a single video by URL or ID — useful for manual testing."""
    vid_m = re.search(
        r'(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})',
        url_or_id,
    )
    vid = vid_m.group(1) if vid_m else (url_or_id if re.match(r'^[A-Za-z0-9_-]{11}$', url_or_id) else None)
    if not vid:
        print(f"Could not extract video ID from: {url_or_id}", file=sys.stderr)
        sys.exit(1)

    video: dict = {
        "video_id":  vid,
        "title":     url_or_id,
        "published": datetime.now(timezone.utc).isoformat(),
        "url":       f"https://www.youtube.com/watch?v={vid}",
    }

    # Try to get title from oEmbed (no API key needed)
    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"
        req = urllib.request.Request(oembed_url, headers={"User-Agent": "OpenClaw/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            video["title"] = data.get("title", url_or_id)
    except Exception:
        pass

    log(f"Single-video mode: {video['title']!r} ({vid})")
    transcript, source_info = fetch_transcript(vid)
    if not transcript:
        log(f"No transcript available ({source_info})")
    # Single-video mode is always synchronous — immediate result
    summary, takeaways = generate_summary(video["title"], transcript)
    path = write_transcript_file(video, transcript, source_info, summary, takeaways)
    log(f"Done — saved to: {path}")


# ---------------------------------------------------------------------------
# Backfill — reprocess stub files
# ---------------------------------------------------------------------------

def backfill_stubs(filenames: list[str]) -> None:
    """
    Reprocess a list of stub transcript files.

    For each filename, reads the file from TRANSCRIPTS_DIR (or as a path),
    extracts the YouTube video ID from the '- Source:' line, removes that ID
    from processed state, then reprocesses the video in sync mode so a full
    transcript and summary are written.

    Usage:
      python3 channel_poller.py --backfill "2026-04-14 - some-video.md" ...
      python3 channel_poller.py --backfill-list /tmp/stubs.txt
    """
    _lock = acquire_lock()
    state = load_state()

    VID_RE = re.compile(
        r'(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})'
    )

    to_process: list[dict] = []
    for fname in filenames:
        p = Path(fname)
        if not p.is_absolute():
            p = TRANSCRIPTS_DIR / fname
        if not p.exists():
            log_err(f"Backfill: file not found — {p}")
            continue

        text = p.read_text(encoding="utf-8", errors="replace")

        # Extract video ID from Source line
        source_line = next(
            (ln for ln in text.splitlines() if ln.strip().lower().startswith("- source:")), ""
        )
        m = VID_RE.search(source_line)
        if not m:
            log_err(f"Backfill: could not extract video ID from {p.name} — skipping")
            continue
        vid = m.group(1)

        # Extract title from first heading
        title_line = next(
            (ln for ln in text.splitlines() if ln.startswith("# ")), ""
        )
        title = title_line.lstrip("# ").strip() or vid

        # Extract published from Received line (best effort)
        received_line = next(
            (ln for ln in text.splitlines() if ln.strip().lower().startswith("- received:")), ""
        )
        published = ""
        date_m = re.search(r'(\d{4}-\d{2}-\d{2})', received_line)
        if date_m:
            published = f"{date_m.group(1)}T00:00:00Z"

        url = f"https://www.youtube.com/watch?v={vid}"
        url_m = re.search(r'https://(?:www\.)?youtube\.com/\S+', source_line)
        if url_m:
            url = url_m.group(0).rstrip(")")

        to_process.append({
            "video_id":  vid,
            "title":     title,
            "published": published,
            "url":       url,
        })
        log(f"Backfill: queued {vid} — {title!r}")

    if not to_process:
        log("Backfill: nothing to reprocess")
        return

    # Remove these IDs from processed state so the sync path will accept them
    processed_ids = set(state.get("processed_ids", []))
    pending_ids   = set(state.get("pending_video_ids", []))
    for v in to_process:
        processed_ids.discard(v["video_id"])
        pending_ids.discard(v["video_id"])
    state["processed_ids"]    = list(processed_ids)
    state["pending_video_ids"] = list(pending_ids)
    save_state(state)

    log(f"Backfill: reprocessing {len(to_process)} video(s) in sync mode…")
    written = 0
    for video in to_process:
        vid = video["video_id"]
        try:
            ok = process_video_sync(video, channel_label="backfill")
            if ok:
                written += 1
        except Exception as e:
            log_err(f"Backfill: failed for {vid}: {e}")
        # Mark done regardless so we don't loop forever on hard failures
        processed_ids.add(vid)
        state["processed_ids"] = list(processed_ids)
        save_state(state)
        time.sleep(2)

    log(f"Backfill complete — {written}/{len(to_process)} reprocessed")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube channel poller for OpenClaw")
    parser.add_argument("--video", metavar="URL_OR_ID",
                        help="Process a single video by URL or ID (always synchronous)")
    parser.add_argument("--sync", action="store_true",
                        help=(
                            "Force synchronous processing — generate summaries immediately "
                            "instead of using the Anthropic batch API. "
                            "Used by /yt-run in mgmt-bot for instant Telegram feedback. "
                            "Costs ~2x vs batch mode."
                        ))
    parser.add_argument("--backfill", nargs="+", metavar="FILENAME",
                        help=(
                            "Reprocess a list of stub transcript filenames. "
                            "Reads video ID from each file's Source line, then reruns "
                            "transcript fetch + summary in sync mode. "
                            "Filenames are relative to the transcripts directory."
                        ))
    parser.add_argument("--backfill-list", metavar="FILE",
                        help=(
                            "Path to a text file listing stub filenames to backfill, "
                            "one per line. Alternative to passing filenames directly."
                        ))
    args = parser.parse_args()

    if args.video:
        process_single_video_url(args.video)
        return

    # Backfill mode — reprocess a list of stub files
    if args.backfill or args.backfill_list:
        filenames: list[str] = list(args.backfill or [])
        if args.backfill_list:
            try:
                extra = Path(args.backfill_list).read_text().splitlines()
                filenames.extend(ln.strip() for ln in extra if ln.strip() and not ln.startswith("#"))
            except Exception as e:
                print(f"Could not read backfill list {args.backfill_list}: {e}", file=sys.stderr)
                sys.exit(1)
        backfill_stubs(filenames)
        return

    _lock = acquire_lock()

    log(f"Poll starting (mode: {'sync' if args.sync else 'batch'})")

    state = load_state()
    state["last_run"] = datetime.now(timezone.utc).isoformat()

    # Phase 1 — check any batches submitted on previous runs
    completed = process_pending_batches(state)
    if completed:
        log(f"Batch results: {completed} transcript(s) written from previous batch(es)")
        save_state(state)

    # Phase 2 — poll for new videos
    new_count = poll_channels(state, sync=args.sync)

    save_state(state)
    if args.sync:
        log(f"Poll complete — {new_count} new transcript(s) written")
    else:
        pending = len(state.get("pending_batches", []))
        log(f"Poll complete — {new_count} video(s) queued in {pending} batch(es), "
            f"{completed} written from prior batch(es)")


if __name__ == "__main__":
    main()
