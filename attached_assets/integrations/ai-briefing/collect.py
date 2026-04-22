#!/usr/bin/env python3
"""
AI Briefing Collector — OpenClaw Integration
=============================================

Polls all configured RSS/Atom feeds, writes raw items to
~/.openclaw/ai-briefing/raw/YYYY-MM-DD.json, and updates
seen-items.json (URL-hash keyed deduplication).

Each source is fetched independently — one failure does not abort the run.
Results (including per-source errors) are written to state.json.

Usage:
  python3 collect.py [--lookback-days N] [--sources path/to/ai-briefing-sources.yaml]

Outputs:
  ~/.openclaw/ai-briefing/raw/YYYY-MM-DD.json    — new items for this run
  ~/.openclaw/ai-briefing/seen-items.json         — cumulative dedup registry
  ~/.openclaw/ai-briefing/state.json              — updated with collection stats
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

STATE_DIR     = Path.home() / ".openclaw"
BRIEFING_DIR  = STATE_DIR / "ai-briefing"
RAW_DIR       = BRIEFING_DIR / "raw"
SEEN_FILE     = BRIEFING_DIR / "seen-items.json"
STATE_FILE    = BRIEFING_DIR / "state.json"

REPO_DIR       = Path.home() / "openclaw"
DEFAULT_SOURCES = REPO_DIR / "reference" / "ai-briefing-sources.yaml"

DEFAULT_LOOKBACK_DAYS = 14
LOG_PREFIX = "[ai-briefing/collect]"


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
# State helpers
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


def load_seen() -> dict:
    return _load_json(SEEN_FILE, {})


def save_seen(seen: dict) -> None:
    _write_json(SEEN_FILE, seen)


def load_state() -> dict:
    return _load_json(STATE_FILE, {})


def save_state(state: dict) -> None:
    _write_json(STATE_FILE, state)


# ---------------------------------------------------------------------------
# Source loading
# ---------------------------------------------------------------------------

def load_sources(sources_path: Path) -> list[dict]:
    """Load feed sources from YAML. Falls back to embedded minimal list."""
    if not sources_path.exists():
        log_err(f"Sources file not found: {sources_path}")
        return []

    if not HAS_YAML:
        log_err("pyyaml not installed — cannot load sources. Run: pip3 install pyyaml")
        return []

    try:
        data = yaml.safe_load(sources_path.read_text())
        sources = data.get("sources", [])
        active = [s for s in sources if s.get("active", True)]
        log(f"Loaded {len(active)} active sources from {sources_path}")
        return active
    except Exception as e:
        log_err(f"Could not parse {sources_path}: {e}")
        return []


# ---------------------------------------------------------------------------
# URL hashing (dedup key)
# ---------------------------------------------------------------------------

def url_hash(url: str) -> str:
    return hashlib.sha1(url.strip().lower().encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Feed fetching
# ---------------------------------------------------------------------------

def _fetch_url_raw(url: str, timeout: int = 20) -> bytes | None:
    """Fetch a URL and return raw bytes, or None on failure."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "OpenClaw-AIBriefing/1.0 (RSS feed reader)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        log_err(f"HTTP {e.code} fetching {url}")
        return None
    except Exception as e:
        log_err(f"Fetch error for {url}: {e}")
        return None


def _parse_with_feedparser(raw: bytes, url: str) -> list[dict]:
    """Parse feed using feedparser library."""
    import feedparser as fp
    d = fp.parse(raw)
    items = []
    for entry in d.entries:
        link = entry.get("link") or entry.get("id") or ""
        title = entry.get("title") or "(no title)"
        summary = entry.get("summary") or entry.get("description") or ""
        # Strip HTML tags from summary (simple approach)
        import re
        summary = re.sub(r"<[^>]+>", " ", summary).strip()
        summary = re.sub(r"\s+", " ", summary)[:500]

        # Parse published date
        published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if published_parsed:
            dt = datetime(*published_parsed[:6], tzinfo=timezone.utc)
            published_iso = dt.isoformat()
        else:
            published_iso = datetime.now(timezone.utc).isoformat()

        if not link:
            continue

        items.append({
            "url": link,
            "title": title,
            "summary": summary,
            "published": published_iso,
        })
    return items


def _parse_with_stdlib(raw: bytes, url: str) -> list[dict]:
    """Fallback XML parser using stdlib when feedparser is unavailable."""
    import re

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        log_err(f"XML parse error for {url}: {e}")
        return []

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }

    items = []

    def _text(el, tag, default=""):
        found = el.find(tag)
        return (found.text or "").strip() if found is not None else default

    def _strip_html(s: str) -> str:
        s = re.sub(r"<[^>]+>", " ", s)
        return re.sub(r"\s+", " ", s).strip()[:500]

    # Atom feeds
    for entry in root.findall("atom:entry", ns):
        link_el = entry.find("atom:link[@rel='alternate']", ns) or entry.find("atom:link", ns)
        link = link_el.attrib.get("href", "") if link_el is not None else ""
        title = _text(entry, "atom:title", "(no title)")
        summary = _text(entry, "atom:summary") or _text(entry, "atom:content")
        published = _text(entry, "atom:published") or _text(entry, "atom:updated") or datetime.now(timezone.utc).isoformat()
        if link:
            items.append({"url": link, "title": title, "summary": _strip_html(summary), "published": published})

    if items:
        return items

    # RSS 2.0 feeds
    for item in root.iter("item"):
        link = _text(item, "link") or _text(item, "guid")
        title = _text(item, "title", "(no title)")
        description = _text(item, "description")
        pub_date = _text(item, "pubDate") or datetime.now(timezone.utc).isoformat()
        if link:
            items.append({"url": link, "title": title, "summary": _strip_html(description), "published": pub_date})

    return items


def _parse_json_feed(raw: bytes) -> list[dict] | None:
    """
    Parse JSON Feed 1.x (https://www.jsonfeed.org/) format.
    Returns list of items or None if the payload is not a JSON Feed.
    """
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return None

    if not isinstance(data, dict) or "items" not in data:
        return None

    import re as _re
    items = []
    for entry in data.get("items", []):
        url = entry.get("url") or entry.get("external_url") or entry.get("id") or ""
        if not url or not url.startswith("http"):
            continue
        title = entry.get("title") or "(no title)"
        content_html = entry.get("content_html") or entry.get("content_text") or entry.get("summary") or ""
        summary = _re.sub(r"<[^>]+>", " ", content_html).strip()
        summary = _re.sub(r"\s+", " ", summary)[:500]
        published = entry.get("date_published") or entry.get("date_modified") or datetime.now(timezone.utc).isoformat()
        items.append({"url": url, "title": title, "summary": summary, "published": published})
    return items


def fetch_feed(source: dict) -> tuple[list[dict], str | None]:
    """
    Fetch and parse a single feed. Returns (items, error_message).
    error_message is None on success.
    """
    url = source.get("url", "")
    name = source.get("name", url)

    if not url:
        return [], f"no URL for source '{name}'"

    raw = _fetch_url_raw(url)
    if raw is None:
        return [], f"fetch failed for '{name}' ({url})"

    try:
        # Try JSON Feed 1.x first — handles *.json endpoints before RSS/XML.
        json_items = _parse_json_feed(raw)
        if json_items is not None:
            items = json_items
        elif HAS_FEEDPARSER:
            items = _parse_with_feedparser(raw, url)
        else:
            items = _parse_with_stdlib(raw, url)
    except Exception as e:
        return [], f"parse error for '{name}': {e}"

    # Enrich each item with source metadata (all parsers go through this path)
    for item in items:
        item["source_name"] = name
        item["source_url"] = url
        item["source_weight"] = source.get("weight", 0.6)
        item["source_category"] = source.get("category", ["general"])

    return items, None


# ---------------------------------------------------------------------------
# Date filtering
# ---------------------------------------------------------------------------

def _parse_date(date_str: str) -> datetime | None:
    """Best-effort parse of various date formats to a UTC datetime."""
    if not date_str or not isinstance(date_str, str):
        return None

    s = date_str.strip()

    # RFC 2822 — most common RSS/Atom pubDate format
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).astimezone(timezone.utc)
    except Exception:
        pass

    # ISO 8601: normalise Z suffix and strip sub-second precision to 6 digits
    iso = s.replace("Z", "+00:00").replace("z", "+00:00")
    # Trim fractional seconds to 6 digits max (Python's fromisoformat limit)
    import re as _re
    iso = _re.sub(r"(\.\d{7,})", lambda m: m.group(0)[:7], iso)
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        pass

    # Explicit strptime fallback for date-only strings (e.g. "2025-01-15")
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y"):
        try:
            dt = datetime.strptime(s[:20], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


def is_within_lookback(item: dict, lookback_days: int) -> bool:
    """Return True if item's published date is within the lookback window."""
    dt = _parse_date(item.get("published", ""))
    if dt is None:
        return True  # unknown date — include by default
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    return dt >= cutoff


# ---------------------------------------------------------------------------
# Main collection logic
# ---------------------------------------------------------------------------

def collect(sources_path: Path, lookback_days: int) -> dict:
    """
    Poll all feeds, deduplicate, write raw output.
    Returns a summary dict for state.json.
    """
    run_start = datetime.now(timezone.utc).isoformat()
    sources = load_sources(sources_path)

    if not sources:
        return {
            "run_start": run_start,
            "error": "no sources loaded",
            "sources_ok": 0,
            "sources_failed": 0,
            "items_total_fetched": 0,
            "items_new": 0,
        }

    seen = load_seen()
    today = datetime.now().strftime("%Y-%m-%d")
    raw_file = RAW_DIR / f"{today}.json"

    all_new_items: list[dict] = []
    total_fetched = 0   # total items retrieved from all feeds before any dedup
    sources_ok = 0
    sources_failed = 0
    source_errors: dict[str, str] = {}

    for source in sources:
        name = source.get("name", source.get("url", "?"))
        log(f"Fetching: {name}")

        items, error = fetch_feed(source)

        if error:
            log_err(f"Source '{name}': {error}")
            sources_failed += 1
            source_errors[name] = error
            continue

        sources_ok += 1
        total_fetched += len(items)
        new_count = 0

        for item in items:
            url = item.get("url", "")
            if not url:
                continue

            if not is_within_lookback(item, lookback_days):
                continue

            key = url_hash(url)
            if key in seen:
                continue

            item["url_hash"] = key
            item["collected_at"] = datetime.now(timezone.utc).isoformat()
            all_new_items.append(item)
            seen[key] = {
                "url": url,
                "title": item.get("title", ""),
                "source": name,
                "collected_at": item["collected_at"],
            }
            new_count += 1

        log(f"  {name}: {len(items)} items fetched, {new_count} new")

    # Abort only if ALL sources failed
    if sources_failed > 0 and sources_ok == 0:
        log_err("All sources failed — aborting collection run")
        return {
            "run_start": run_start,
            "error": "all sources failed",
            "sources_ok": 0,
            "sources_failed": sources_failed,
            "source_errors": source_errors,
            "items_total_fetched": 0,
            "items_new": 0,
        }

    # Write raw output — merge-safe across same-day reruns.
    # Existing items in today's raw file are preserved so that a failed
    # rank/synthesize run followed by a same-day retry never loses
    # previously fetched-but-unbriefed items.
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    existing_raw: list[dict] = []
    if raw_file.exists():
        try:
            existing_raw = _load_json(raw_file, [])
            if not isinstance(existing_raw, list):
                existing_raw = []
        except Exception:
            existing_raw = []
    existing_hashes = {item.get("url_hash") for item in existing_raw if item.get("url_hash")}
    truly_new = [it for it in all_new_items if it.get("url_hash") not in existing_hashes]
    merged_items = existing_raw + truly_new
    _write_json(raw_file, merged_items)
    log(f"Raw file: {len(existing_raw)} existing + {len(truly_new)} new = "
        f"{len(merged_items)} total items in {raw_file}")

    # Update seen-items
    save_seen(seen)
    log(f"seen-items.json now has {len(seen)} entries")

    summary = {
        "run_start": run_start,
        "raw_file": str(raw_file),
        "sources_ok": sources_ok,
        "sources_failed": sources_failed,
        "source_errors": source_errors,
        "items_total_fetched": total_fetched,  # all items from feeds before dedup/lookback
        "items_new": len(all_new_items),        # new items fetched this run (deduped by seen)
        "lookback_days": lookback_days,
    }

    if sources_failed > 0:
        log(f"WARNING: {sources_failed} source(s) failed — partial run. Continuing.")

    return summary


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AI Briefing Collector")
    p.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                   help=f"Max age of items to include (default: {DEFAULT_LOOKBACK_DAYS})")
    p.add_argument("--sources", type=Path, default=DEFAULT_SOURCES,
                   help=f"Path to ai-briefing-sources.yaml (default: {DEFAULT_SOURCES})")
    return p.parse_args()


def main() -> dict:
    args = parse_args()

    if not HAS_FEEDPARSER:
        log("WARNING: feedparser not installed — using stdlib XML parser (less robust)")
        log("         Install: pip3 install --break-system-packages feedparser")

    if not HAS_YAML:
        log_err("pyyaml not installed. Install: pip3 install --break-system-packages pyyaml")
        sys.exit(1)

    log(f"Starting collection (lookback: {args.lookback_days} days)")
    summary = collect(args.sources, args.lookback_days)

    # Merge into state.json
    state = load_state()
    state["collect"] = summary
    save_state(state)

    if summary.get("error") == "no sources loaded":
        log_err("Collection failed — no sources could be loaded (missing/bad YAML?)")
        sys.exit(1)

    if summary.get("error") == "all sources failed":
        log_err("Collection failed — all sources returned errors")
        sys.exit(1)

    log(f"Collection complete: {summary['items_total_fetched']} fetched, "
        f"{summary['items_new']} new across {summary['sources_ok']} sources")
    return summary


if __name__ == "__main__":
    main()
