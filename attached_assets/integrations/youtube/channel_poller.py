#!/usr/bin/env python3
"""
YouTube Channel Poller — OpenClaw Integration
==============================================

WHAT THIS DOES
--------------
Polls one or more YouTube channels for new videos via their public RSS feeds.
For watched-channel videos in normal cron mode it:
  1. Fetches the transcript/captions immediately (via youtube-transcript-api, no API key)
  2. Writes a formatted Markdown resource file immediately with a placeholder
     summary layer showing that a cheaper batch summary is pending
  3. Queues the richer AI summary + key takeaways work for Anthropic batch
     processing once enough items accumulate or the oldest item has waited long enough
  4. When the batch result comes back later, overwrites the same resource file
     in place with the finished Useful Summary and Key Takeaways
  5. Sends Telegram notifications for capture-now and batch-complete states

For manual / urgent single-video runs (for example --video, --sync, or OpenAI
fallback mode), it still processes synchronously and writes the finished file
in one pass.

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
import subprocess
import sys
import tempfile
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
YOUTUBE_VENV = INTEGRATIONS / ".venv"
WHISPER_SCRIPT = Path.home() / "openclaw" / "skills" / "openai-whisper-api" / "scripts" / "transcribe.sh"

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
# Cheaper-watch-channel mode: capture transcript immediately, but only submit
# AI summaries once enough items accumulate or the oldest has waited a while.
BATCH_SUBMIT_MIN_ITEMS   = 4
BATCH_SUBMIT_MAX_AGE_HOURS = 6

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
            data.setdefault("pending_summary_items", [])
            # De-duplicate any queued summary items by video_id (keep first seen).
            # Older state files may contain repeated entries for the same video from
            # the pre-fix duplicate-capture bug; collapse them so the next batch does
            # not emit one notification per duplicate.
            seen_ids: set[str] = set()
            deduped_items = []
            for it in data["pending_summary_items"]:
                vid = it.get("video_id")
                if vid and vid in seen_ids:
                    continue
                if vid:
                    seen_ids.add(vid)
                deduped_items.append(it)
            data["pending_summary_items"] = deduped_items
            return data
    except Exception as e:
        log(f"WARNING: Could not read state: {e} — starting fresh")
    return {"processed_ids": [], "pending_video_ids": [], "pending_batches": [], "pending_summary_items": [], "last_run": None}


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


def _fetch_youtube_page_html(handle_or_url: str) -> tuple[str, str]:
    """Return (fetch_url, html) for a YouTube channel/page-like URL, or ('','') on failure."""
    handle_m = re.search(r'youtube\.com/@([\w.-]+)', handle_or_url)
    if handle_m:
        fetch_url = f"https://www.youtube.com/@{handle_m.group(1)}"
    elif handle_or_url.startswith("http"):
        fetch_url = handle_or_url.split("?")[0]
    else:
        return "", ""

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
        return fetch_url, html
    except Exception as e:
        log_err(f"Handle resolution fetch failed for {fetch_url}: {e}")
        return "", ""


def _resolve_handle_to_channel_id(handle_or_url: str) -> str:
    """
    Fetch a YouTube @handle or channel page and extract the UC... channel ID.
    YouTube embeds channelId in its page JSON — no API key needed.
    Returns '' if resolution fails.
    """
    fetch_url, html = _fetch_youtube_page_html(handle_or_url)
    if not html:
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


def _resolve_channel_feed_id(handle_or_url: str) -> str:
    """Prefer the RSS channel_id advertised by the page itself."""
    fetch_url, html = _fetch_youtube_page_html(handle_or_url)
    if not html:
        return ""
    m = re.search(r'https://www\.youtube\.com/feeds/videos\.xml\?channel_id=([A-Za-z0-9_-]+)', html)
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
    Prefer the feed ID advertised by the page itself when a channel_url exists,
    because it can differ from page JSON channelId on some channels.
    """
    url = (ch.get("channel_url") or "").strip().rstrip("/")

    if url:
        feed_id = _resolve_channel_feed_id(url)
        if feed_id:
            if ch.get("channel_id") and ch.get("channel_id").strip() != feed_id:
                log(f"  RSS feed id differs from configured channel_id; using page-advertised feed id {feed_id} (from {url})")
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={feed_id}"

    channel_id = resolve_channel_id(ch)
    if channel_id:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    # Last-resort legacy fallback for old /user/ style channels
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
    raw = None
    headers_to_try = [
        {"User-Agent": "OpenClaw-YouTubePoller/1.0"},
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    ]
    last_err = None
    for headers in headers_to_try:
        try:
            req = urllib.request.Request(rss_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
            break
        except urllib.error.HTTPError as e:
            last_err = e
            continue
        except Exception as e:
            last_err = e
            continue

    if raw is None:
        if isinstance(last_err, urllib.error.HTTPError):
            log_err(f"HTTP {last_err.code} fetching RSS {rss_url}")
        else:
            log_err(f"Error fetching RSS {rss_url}: {last_err}")
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


def fetch_videos_from_channel_page(channel_url: str, max_items: int = 15) -> list[dict]:
    """Fallback when RSS is broken: scrape recent video IDs from the channel videos page."""
    base_url = channel_url.split("?")[0].rstrip("/")
    page_url = base_url if base_url.endswith("/videos") else f"{base_url}/videos"
    try:
        req = urllib.request.Request(
            page_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log_err(f"Channel page fallback failed for {page_url}: {e}")
        return []

    video_ids = []
    for vid in re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html):
        if vid not in video_ids:
            video_ids.append(vid)
        if len(video_ids) >= max_items:
            break

    videos = []
    for vid in video_ids:
        meta = fetch_video_metadata(vid)
        title = meta.get("title") or f"https://www.youtube.com/watch?v={vid}"
        published = meta.get("published") or ""
        videos.append({
            "video_id": vid,
            "channel_id": "",
            "title": title,
            "published": published,
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    return videos


# ---------------------------------------------------------------------------
# Transcript fetch (via youtube-transcript-api)
# ---------------------------------------------------------------------------

def _fallback_transcribe_via_whisper(video_id: str) -> tuple[str, str]:
    """Download audio and transcribe via the Whisper skill script."""
    yt_dlp_bin = YOUTUBE_VENV / "bin" / "yt-dlp"
    if not yt_dlp_bin.exists():
        return "", "whisper fallback unavailable — yt-dlp missing"
    if not WHISPER_SCRIPT.exists():
        return "", "whisper fallback unavailable — script missing"
    if not os.environ.get("OPENAI_API_KEY"):
        return "", "whisper fallback unavailable — OPENAI_API_KEY missing"

    with tempfile.TemporaryDirectory(prefix="yt-audio-") as tmpdir:
        tmp = Path(tmpdir)
        audio_base = tmp / video_id
        audio_out = str(audio_base) + ".%(ext)s"
        audio_file = tmp / f"{video_id}.mp3"
        transcript_file = tmp / f"{video_id}.txt"

        download_cmd = [
            str(yt_dlp_bin),
            "-x",
            "--audio-format", "mp3",
            "-o", audio_out,
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        try:
            proc = subprocess.run(download_cmd, capture_output=True, text=True, timeout=300)
            if proc.returncode != 0:
                return "", f"whisper fallback download failed: {proc.stderr.strip()[:200]}"
        except Exception as e:
            return "", f"whisper fallback download error: {e}"

        if not audio_file.exists():
            mp3s = list(tmp.glob("*.mp3"))
            if mp3s:
                audio_file = mp3s[0]
        if not audio_file.exists():
            return "", "whisper fallback download produced no audio file"

        transcribe_cmd = [
            str(WHISPER_SCRIPT),
            str(audio_file),
            "--language", "en",
            "--out", str(transcript_file),
        ]
        try:
            proc = subprocess.run(transcribe_cmd, capture_output=True, text=True, timeout=900, env=os.environ.copy())
            if proc.returncode != 0:
                return "", f"whisper fallback transcription failed: {proc.stderr.strip()[:200]}"
        except Exception as e:
            return "", f"whisper fallback transcription error: {e}"

        try:
            text = transcript_file.read_text(encoding="utf-8", errors="replace").strip()
        except Exception as e:
            return "", f"whisper fallback read error: {e}"

        if not text:
            return "", "whisper fallback returned empty transcript"
        return text, "whisper fallback"


def fetch_transcript(video_id: str) -> tuple[str, str]:
    """
    Returns (transcript_text, source_info).
    transcript_text is empty string if no transcript available.
    Supports both older and newer youtube-transcript-api interfaces.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        log_err("youtube-transcript-api not installed — cannot fetch transcript")
        log_err("Fix: pip3 install --break-system-packages youtube-transcript-api")
        return "", "library not installed"

    langs = [l.strip() for l in os.environ.get("YOUTUBE_POLL_LANGS", "en").split(",") if l.strip()]

    try:
        # Old API exposed classmethods like list_transcripts(); newer releases use
        # an instance with .list() / .fetch(). Support both so the poller survives
        # package upgrades without silently degrading to stub files.
        if hasattr(YouTubeTranscriptApi, "list_transcripts"):
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        else:
            transcript_list = YouTubeTranscriptApi().list(video_id)
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
        fallback_text, fallback_info = _fallback_transcribe_via_whisper(video_id)
        if fallback_text:
            return fallback_text, fallback_info
        return "", fallback_info or "fetch failed"

    parts = []
    for entry in transcript:
        if isinstance(entry, dict):
            text = (entry.get("text") or "").strip()
        else:
            text = (getattr(entry, "text", "") or "").strip()
        if text:
            parts.append(text)

    return " ".join(parts), source_info


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------

def fetch_video_metadata(video_id: str) -> dict:
    """Best-effort metadata lookup for title + published date."""
    meta = {"title": "", "published": ""}

    # Fast title path via oEmbed
    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        req = urllib.request.Request(oembed_url, headers={"User-Agent": "OpenClaw/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            meta["title"] = (data.get("title") or "").strip()
    except Exception:
        pass

    # Publish-date path via watch page
    try:
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        req = urllib.request.Request(
            watch_url,
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        m = re.search(r'"dateText":\{"simpleText":"([^"]+)"\}', html)
        if m:
            raw_date = m.group(1).strip()
            raw_date = re.sub(r'^Streamed live on\s+', '', raw_date)
            raw_date = re.sub(r'^Premiered\s+', '', raw_date)
            try:
                dt = datetime.strptime(raw_date, "%b %d, %Y")
                meta["published"] = dt.strftime("%Y-%m-%dT00:00:00+00:00")
            except Exception:
                pass

        if not meta["title"]:
            m = re.search(r'<title>(.*?)</title>', html, re.S)
            if m:
                meta["title"] = m.group(1).replace(" - YouTube", "").strip()
    except Exception:
        pass

    return meta


def fetch_video_title(video_id: str) -> str:
    return fetch_video_metadata(video_id).get("title", "")


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
    raw = ""
    if has_anthropic:
        raw = _call_anthropic_sync(prompt)
        if not raw and has_openai:
            log("Anthropic summary failed — falling back to OpenAI")
            raw = _call_openai(prompt)
    elif has_openai:
        raw = _call_openai(prompt)

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


def should_submit_summary_batch(state: dict) -> bool:
    pending_items = state.get("pending_summary_items", [])
    if not pending_items:
        return False
    if len(pending_items) >= BATCH_SUBMIT_MIN_ITEMS:
        return True
    first_seen = pending_items[0].get("queued_at", "")
    try:
        age_hours = (datetime.now(timezone.utc) - datetime.fromisoformat(first_seen)).total_seconds() / 3600
    except Exception:
        age_hours = 0
    return age_hours >= BATCH_SUBMIT_MAX_AGE_HOURS


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
                overwrite_path = Path(v["resource_path"]) if v.get("resource_path") else None
                write_transcript_file(
                    video       = v,
                    transcript  = v.get("transcript", ""),
                    source_info = v.get("source_info", ""),
                    summary     = summary,
                    takeaways   = takeaways,
                    overwrite_path = overwrite_path,
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
                           summary: str, takeaways: str,
                           overwrite_path: Path | None = None) -> Path:
    """Write the formatted resource file. Returns the path written."""
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    title = video.get("title") or video.get("video_id", "untitled")
    slug  = make_slug(title)

    # Parse published date for canonical file naming, but keep a separate
    # processed timestamp so backfilled/late transcripts do not pretend they
    # were received on publication day.
    pub_raw = video.get("published", "")
    processed_str = _london_time(datetime.now(timezone.utc).replace(tzinfo=None))
    published_str = ""
    try:
        dt = datetime.fromisoformat(pub_raw.replace("Z", "+00:00"))
        date_str = dt.strftime("%Y-%m-%d")
        published_str = dt.strftime("%Y-%m-%d")
    except Exception:
        dt = datetime.now(timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")

    filename = f"{date_str} - {slug}.md"
    path = overwrite_path or (TRANSCRIPTS_DIR / filename)

    # Avoid overwriting if file already exists (e.g. duplicate slug), unless we
    # are intentionally repairing/backfilling an existing resource file in place.
    if overwrite_path is None and path.exists():
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

    meta_lines = [
        f"# {title}",
        f"- Processed: {processed_str} Europe/London",
        f"- Source: {url}",
        f"- Topic: {topic}",
        f"- Status: resource",
        f"- Transcript: {transcript_status}",
    ]
    if published_str:
        meta_lines.insert(1, f"- Published: {published_str}")

    content = (
        "\n".join(meta_lines) + "\n"
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
            candidate = str(allow_from[0])
            chat_id = candidate.split(":", 1)[1] if ":" in candidate else candidate
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

def write_pending_transcript_resource(video: dict, transcript: str, source_info: str, channel_label: str) -> Path:
    summary = (
        "- Transcript captured immediately from the watched channel.\n"
        f"- AI summary deferred to cheaper batch processing.\n"
        f"- Channel: {channel_label}"
    )
    takeaways = "- Awaiting cheaper batch summary."
    return write_transcript_file(video, transcript, source_info, summary, takeaways)


def process_video_sync(video: dict, channel_label: str, overwrite_path: Path | None = None) -> bool:
    """Fetch transcript, generate summary synchronously, write file, notify."""
    vid   = video["video_id"]
    title = video.get("title", vid)

    log(f"Processing (sync): {title!r} ({vid})")

    transcript, source_info = fetch_transcript(vid)
    if not transcript:
        log(f"  No transcript ({source_info}) — saving stub file")

    summary, takeaways = generate_summary(title, transcript)
    path = write_transcript_file(video, transcript, source_info, summary, takeaways, overwrite_path=overwrite_path)

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
      Transcripts are fetched and written immediately as placeholder resources,
      then queued for Anthropic Message Batches API submission (50% cheaper)
      only once enough items accumulate or the oldest queued item has waited
      long enough. Finished summaries are written back onto the same files on
      a later poll run. Falls back to synchronous processing when only OpenAI
      is available.

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
    # only when Anthropic is absent. If Anthropic auth is broken, let batch submit
    # fail explicitly and then fall back, rather than silently bypassing the 50%-cheaper path.
    if not has_anthropic:
        sync = True

    processed_ids = set(state.get("processed_ids", []))
    pending_ids   = set(state.get("pending_video_ids", []))
    # Also treat anything already queued for a (not-yet-submitted) batch as claimed,
    # so a video captured on a previous run is never re-captured/re-notified even if
    # pending_video_ids was not persisted for some reason.
    queued_summary_ids = {
        it.get("video_id")
        for it in state.get("pending_summary_items", [])
        if it.get("video_id")
    }
    pending_ids  |= queued_summary_ids
    claimed_ids   = processed_ids | pending_ids  # don't re-process any of these
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
        if not videos and ch.get("channel_url"):
            fallback_videos = fetch_videos_from_channel_page(ch["channel_url"])
            if fallback_videos:
                videos = fallback_videos
                log(f"  Channel page fallback returned {len(videos)} video(s)")

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
                log(f"  Capturing transcript now, deferring AI batch summary: {title!r}")
                try:
                    transcript, source_info = fetch_transcript(vid)
                    pending_video = {
                        "custom_id":     f"vid_{vid}",
                        "video_id":      vid,
                        "title":         title,
                        "transcript":    transcript,
                        "source_info":   source_info,
                        "published":     video.get("published", ""),
                        "url":           video.get("url", f"https://www.youtube.com/watch?v={vid}"),
                        "channel_label": label,
                        "channel_id":    video.get("channel_id", ""),
                        "queued_at":     datetime.now(timezone.utc).isoformat(),
                    }
                    pending_path = write_pending_transcript_resource(video, transcript, source_info, label)
                    pending_video["resource_path"] = str(pending_path)
                    state.setdefault("pending_summary_items", []).append(pending_video)
                    pending_ids.add(vid)
                    claimed_ids.add(vid)
                    channel_new += 1
                    new_count += 1
                    notify(
                        f"📺 Transcript captured (summary queued for cheaper batch)\n"
                        f"Channel: {label}\n"
                        f"Title: {title}\n"
                        f"Source: {video.get('url', '')}"
                    )
                except Exception as e:
                    log_err(f"  Failed collecting {vid} for batch ({title!r}): {e} — skipping")
                    processed_ids.add(vid)
                    claimed_ids.add(vid)
                time.sleep(1)

        if channel_new == 0:
            log(f"  No new videos for {label}")

    # ── Submit accumulated cheaper batch only when worth it ───────────────
    pending_summary_items = state.get("pending_summary_items", [])
    if pending_summary_items and should_submit_summary_batch(state):
        log(f"Submitting Anthropic batch for {len(pending_summary_items)} queued video(s)…")
        batch_id = submit_anthropic_batch(pending_summary_items)
        if batch_id:
            state.setdefault("pending_batches", []).append({
                "batch_id":     batch_id,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "videos":       pending_summary_items,
            })
            state["pending_summary_items"] = []
            log("  Batch queued — summaries will arrive on a later poll run")
        else:
            log("  Batch submit failed — leaving queued items in pending_summary_items for retry")

    # Always persist the claimed (pending) video IDs, whether or not a batch was
    # submitted this run. Otherwise a video captured on a quiet channel (where the
    # batch threshold isn't met) is never recorded as pending, so the next cron run
    # re-captures and re-notifies the same video — the duplicate-notification bug.
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

    meta = fetch_video_metadata(vid)
    video: dict = {
        "video_id":  vid,
        "title":     meta.get("title") or url_or_id,
        "published": meta.get("published") or datetime.now(timezone.utc).isoformat(),
        "url":       f"https://www.youtube.com/watch?v={vid}",
    }

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

        # Extract published date from frontmatter when available
        published_line = next(
            (ln for ln in text.splitlines() if ln.strip().lower().startswith("- published:")), ""
        )
        processed_line = next(
            (ln for ln in text.splitlines() if ln.strip().lower().startswith("- processed:")), ""
        )
        received_line = next(
            (ln for ln in text.splitlines() if ln.strip().lower().startswith("- received:")), ""
        )
        published = ""
        date_m = (
            re.search(r'(\d{4}-\d{2}-\d{2})', published_line)
            or re.search(r'(\d{4}-\d{2}-\d{2})', received_line)
            or re.search(r'(\d{4}-\d{2}-\d{2})', processed_line)
        )
        if date_m:
            published = f"{date_m.group(1)}T00:00:00Z"

        url = f"https://www.youtube.com/watch?v={vid}"
        url_m = re.search(r'https://(?:www\.)?youtube\.com/\S+', source_line)
        if url_m:
            url = url_m.group(0).rstrip(")")

        if not published:
            meta = fetch_video_metadata(vid)
            published = meta.get("published", "") or published
            if title == vid and meta.get("title"):
                title = meta["title"]

        to_process.append({
            "video_id":  vid,
            "title":     title,
            "published": published,
            "url":       url,
            "overwrite_path": str(p),
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
            ok = process_video_sync(
                video,
                channel_label="backfill",
                overwrite_path=Path(video["overwrite_path"]) if video.get("overwrite_path") else None,
            )
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
        pending_batches = len(state.get("pending_batches", []))
        queued_items = len(state.get("pending_summary_items", []))
        log(f"Poll complete — {new_count} transcript(s) captured now, {queued_items} waiting for cheaper batch summary, {pending_batches} batch(es) in flight, {completed} written from prior batch(es)")


if __name__ == "__main__":
    main()
