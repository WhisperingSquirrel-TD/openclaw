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
DEFAULT_AI_MODEL = "claude-haiku-4-5"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
OPENAI_API_URL    = "https://api.openai.com/v1/chat/completions"

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
            return json.loads(STATE_FILE.read_text())
    except Exception as e:
        log(f"WARNING: Could not read state: {e} — starting fresh")
    return {"processed_ids": [], "last_run": None}


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


def resolve_channel_id(ch: dict) -> str | None:
    """Return the channel ID from a channel entry, resolving handles if needed."""
    if ch.get("channel_id"):
        return ch["channel_id"].strip()

    url = (ch.get("channel_url") or "").strip().rstrip("/")
    # Direct channel ID in URL
    m = re.search(r'/channel/(UC[\w-]+)', url)
    if m:
        return m.group(1)

    # For @handle, /c/name, /user/name — we use the RSS feed via URL directly
    # YouTube provides feeds at: https://www.youtube.com/feeds/videos.xml?channel_id=...
    # For handles, we need to resolve via the page. Use a simpler approach:
    # store the URL and fetch RSS via the alternate handle endpoint.
    return None  # signal to caller to use channel_url directly


def rss_url_for_channel(ch: dict) -> str:
    channel_id = resolve_channel_id(ch)
    if channel_id:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    # Handle @username, /c/name, /user/name style URLs
    url = (ch.get("channel_url") or "").strip().rstrip("/")
    # Try to extract handle
    m = re.search(r'/@([\w.-]+)', url)
    if m:
        return f"https://www.youtube.com/feeds/videos.xml?user={m.group(1)}"
    m = re.search(r'/(?:c|user)/([\w.-]+)', url)
    if m:
        return f"https://www.youtube.com/feeds/videos.xml?user={m.group(1)}"

    log_err(f"Cannot resolve RSS URL for channel: {ch}")
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
# AI summary generation
# ---------------------------------------------------------------------------

def _call_anthropic(prompt: str) -> str:
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
    Returns (summary_bullets, takeaways_bullets).
    Both are markdown bullet lists ready to paste into the file.
    Returns placeholder strings if no API key available.
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

    # Truncate transcript for the prompt — keep costs low
    transcript_preview = transcript[:6000]
    if len(transcript) > 6000:
        transcript_preview += " [...transcript truncated for summary...]"

    prompt = (
        f"You are summarising a YouTube video transcript for a personal knowledge base.\n\n"
        f"Video title: {title}\n\n"
        f"Transcript:\n{transcript_preview}\n\n"
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

    raw = _call_anthropic(prompt) if has_anthropic else _call_openai(prompt)

    if not raw:
        return (
            "- Summary generation failed — API call returned empty.",
            "- Takeaways generation failed — API call returned empty.",
        )

    # Parse the response
    summary_lines = []
    takeaway_lines = []
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

    summary   = "\n".join(summary_lines)   or "- See raw transcript below."
    takeaways = "\n".join(takeaway_lines)  or "- See raw transcript below."
    return summary, takeaways


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

    content = (
        f"# {title}\n"
        f"- Received: {received_str} Europe/London\n"
        f"- Source: {url}\n"
        f"- Topic: {topic}\n"
        f"- Status: resource\n"
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
    try:
        payload = json.dumps({"chat_id": chat_id, "text": msg}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log_err(f"Telegram notify failed: {e}")


# ---------------------------------------------------------------------------
# Process a single video
# ---------------------------------------------------------------------------

def process_video(video: dict, channel_label: str, state: dict) -> bool:
    """Fetch transcript, generate summary, write file. Returns True on success."""
    vid   = video["video_id"]
    title = video.get("title", vid)

    log(f"Processing: {title!r} ({vid})")

    transcript, source_info = fetch_transcript(vid)
    if not transcript:
        log(f"  No transcript ({source_info}) — saving stub file")

    summary, takeaways = generate_summary(title, transcript)

    path = write_transcript_file(video, transcript, source_info, summary, takeaways)

    label = channel_label or "YouTube"
    slug  = path.stem  # filename without .md
    notify(
        f"📺 New transcript saved\n"
        f"Channel: {label}\n"
        f"Title: {title}\n"
        f"File: {slug}\n"
        f"Source: {video.get('url', '')}"
    )

    return True


# ---------------------------------------------------------------------------
# Main poll loop
# ---------------------------------------------------------------------------

def poll_channels(state: dict) -> int:
    channels = load_channels()
    if not channels:
        log("No channels configured — nothing to poll")
        return 0

    processed_ids = set(state.get("processed_ids", []))
    cutoff = datetime.now(timezone.utc) - timedelta(days=INITIAL_LOOKBACK_DAYS)
    new_count = 0

    for ch in channels:
        label = ch.get("label", ch.get("channel_id", ch.get("channel_url", "unknown")))
        rss = rss_url_for_channel(ch)
        if not rss:
            continue

        log(f"Polling channel: {label}")
        videos = fetch_rss(rss)
        log(f"  RSS returned {len(videos)} video(s)")

        # Sort oldest-first so we process in chronological order
        def _pub_dt(v):
            try:
                return datetime.fromisoformat(v["published"].replace("Z", "+00:00"))
            except Exception:
                return datetime.min.replace(tzinfo=timezone.utc)

        videos.sort(key=_pub_dt)

        channel_new = 0
        for video in videos:
            vid = video["video_id"]
            if vid in processed_ids:
                continue

            pub_dt = _pub_dt(video)
            if pub_dt != datetime.min.replace(tzinfo=timezone.utc) and pub_dt < cutoff:
                # Older than lookback window — mark as seen but don't process
                processed_ids.add(vid)
                continue

            if channel_new >= MAX_PER_CHANNEL:
                log(f"  Hit MAX_PER_CHANNEL={MAX_PER_CHANNEL} — will catch remaining next run")
                break

            try:
                ok = process_video(video, label, state)
                if ok:
                    new_count += 1
                    channel_new += 1
            except Exception as e:
                log_err(f"  Failed to process {vid}: {e}")

            processed_ids.add(vid)
            state["processed_ids"] = list(processed_ids)
            save_state(state)

            # Brief pause between videos to avoid hammering transcript API
            time.sleep(2)

        if channel_new == 0:
            log(f"  No new videos for {label}")

    # Cap processed_ids to avoid unbounded growth (keep last 5000)
    ids_list = list(processed_ids)
    if len(ids_list) > 5000:
        ids_list = ids_list[-5000:]
    state["processed_ids"] = ids_list
    return new_count


# ---------------------------------------------------------------------------
# Single-video mode (--video flag)
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

    video = {
        "video_id":  vid,
        "title":     url_or_id,  # will be replaced by RSS title if available
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
    summary, takeaways = generate_summary(video["title"], transcript)
    path = write_transcript_file(video, transcript, source_info, summary, takeaways)
    log(f"Done — saved to: {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube channel poller for OpenClaw")
    parser.add_argument("--video", metavar="URL_OR_ID",
                        help="Process a single video by URL or ID (test mode)")
    args = parser.parse_args()

    if args.video:
        process_single_video_url(args.video)
        return

    _lock = acquire_lock()

    log("Poll starting")

    state = load_state()
    state["last_run"] = datetime.now(timezone.utc).isoformat()

    new_count = poll_channels(state)

    save_state(state)
    log(f"Poll complete — new transcripts: {new_count}")


if __name__ == "__main__":
    main()
