#!/usr/bin/env python3
"""
AI Briefing Ranker — OpenClaw Integration
==========================================

Takes the latest raw collection batch, applies heuristic pre-filters, then
sends the narrowed candidate set to Claude Haiku for consulting-relevance
scoring. Falls back to heuristic-only ranking if Haiku fails.

Input:
  ~/.openclaw/ai-briefing/raw/YYYY-MM-DD.json    (latest raw batch)
  ~/.openclaw/ai-briefing/included-items.json     (what's already been briefed)
  reference/AI-BRIEFING-POLICY.md                (scoring guidance for Haiku)

Output:
  ~/.openclaw/ai-briefing/ranked/YYYY-MM-DD.json  (top 5–8 shortlisted items)
  ~/.openclaw/ai-briefing/state.json              (updated with ranking stats)

Usage:
  python3 rank.py [--raw-file path] [--top-n N]
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

STATE_DIR       = Path.home() / ".openclaw"
BRIEFING_DIR    = STATE_DIR / "ai-briefing"
RAW_DIR         = BRIEFING_DIR / "raw"
RANKED_DIR      = BRIEFING_DIR / "ranked"
INCLUDED_FILE   = BRIEFING_DIR / "included-items.json"
STATE_FILE      = BRIEFING_DIR / "state.json"
POLICY_FILE     = Path.home() / "openclaw" / "reference" / "AI-BRIEFING-POLICY.md"

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
HAIKU_MODEL       = "claude-haiku-4-5"
MAX_CANDIDATES_FOR_MODEL = 25  # never send more than this to Haiku
DEFAULT_TOP_N    = 7
NOTHING_IMPORTANT_THRESHOLD = 2  # fewer than this → quiet week
MAX_LOOKBACK_DAYS = 14           # never consider items older than this (cadence-slip guard)
LOG_PREFIX = "[ai-briefing/rank]"


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
# Load API key
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


def _anthropic_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()


# ---------------------------------------------------------------------------
# Step 1: Load raw items — aggregate since last briefing
# ---------------------------------------------------------------------------

def find_latest_raw_file() -> Path | None:
    if not RAW_DIR.exists():
        return None
    files = sorted(RAW_DIR.glob("*.json"), reverse=True)
    return files[0] if files else None


def load_raw_items(raw_file: Path) -> list[dict]:
    items = _load_json(raw_file, [])
    if not isinstance(items, list):
        return []
    return items


def _load_state_for_rank() -> dict:
    state_data = _load_json(STATE_FILE, {})
    return state_data if isinstance(state_data, dict) else {}


def load_raw_items_since_last_briefing() -> list[dict]:
    """
    Aggregate raw items from all raw files created since the last briefing date.
    This ensures items that were fetched but not briefed (e.g., due to pipeline
    failure or a quiet week) are re-evaluated in the next run.
    Falls back to only the latest file if no state is available.
    Deduplicates by url_hash within the aggregated set.
    """
    state = _load_state_for_rank()
    last_briefing_date = state.get("last_briefing_date", "")

    if not RAW_DIR.exists():
        return []

    all_raw_files = sorted(RAW_DIR.glob("*.json"), reverse=True)
    if not all_raw_files:
        return []

    # Hard lookback cap: never consider files older than MAX_LOOKBACK_DAYS
    today = datetime.now()
    hard_cutoff = (today - timedelta(days=MAX_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    # Determine which files are new since the last briefing
    if last_briefing_date:
        # Use the more recent of last_briefing_date and hard_cutoff
        cutoff = max(last_briefing_date, hard_cutoff)
        relevant_files = [f for f in all_raw_files if f.stem >= cutoff]
        if not relevant_files:
            return []
        log(f"Aggregating {len(relevant_files)} raw file(s) since {cutoff} "
            f"(last_briefing={last_briefing_date}, hard_cutoff={hard_cutoff})")
    else:
        # First run — use only the latest file to avoid overwhelming the ranker
        relevant_files = all_raw_files[:1]
        log(f"No last_briefing_date — using latest raw file: {relevant_files[0].name}")

    # Aggregate and deduplicate by url_hash
    seen: set[str] = set()
    aggregated: list[dict] = []
    for f in relevant_files:
        batch = _load_json(f, [])
        if not isinstance(batch, list):
            continue
        for item in batch:
            key = item.get("url_hash") or item.get("url", "")
            if key and key not in seen:
                seen.add(key)
                aggregated.append(item)

    log(f"Aggregated {len(aggregated)} unique items from {len(relevant_files)} raw file(s)")
    return aggregated


# ---------------------------------------------------------------------------
# Step 2: Filter items already included in a previous briefing
# ---------------------------------------------------------------------------

def load_included_data() -> tuple[set[str], list[set[str]]]:
    """Return (url_hash_set, list_of_title_token_sets) from included-items.json."""
    included = _load_json(INCLUDED_FILE, {})
    if not isinstance(included, dict):
        return set(), []
    hashes: set[str] = set(included.keys())
    token_sets: list[set[str]] = []
    for entry in included.values():
        tokens = entry.get("title_tokens") if isinstance(entry, dict) else None
        if tokens and isinstance(tokens, list):
            token_sets.append(set(tokens))
    return hashes, token_sets


def _sig_words(title: str) -> set[str]:
    stopwords = {"the", "a", "an", "and", "or", "in", "on", "for", "of",
                 "to", "with", "from", "is", "are", "as", "it", "its",
                 "how", "why", "what", "by", "at", "be", "this", "that", "has"}
    words = re.findall(r"[a-z]{3,}", title.lower())
    return {w for w in words if w not in stopwords}


def filter_already_included(items: list[dict],
                             included_hashes: set[str],
                             included_token_sets: list[set[str]]) -> list[dict]:
    """
    Drop items already in a previous briefing by URL hash OR topic fingerprint.
    Topic match: ≥ 3 significant title words overlap with any included story.
    """
    TOPIC_OVERLAP_THRESHOLD = 3
    kept = []
    removed_hash = 0
    removed_topic = 0
    for item in items:
        if item.get("url_hash", "") in included_hashes:
            removed_hash += 1
            continue
        if included_token_sets:
            candidate_tokens = _sig_words(item.get("title", ""))
            if any(len(candidate_tokens & ts) >= TOPIC_OVERLAP_THRESHOLD
                   for ts in included_token_sets):
                removed_topic += 1
                continue
        kept.append(item)
    if removed_hash:
        log(f"Filtered {removed_hash} item(s) by URL hash (already briefed)")
    if removed_topic:
        log(f"Filtered {removed_topic} item(s) by topic fingerprint (story already covered)")
    return kept


# ---------------------------------------------------------------------------
# Step 3: Heuristic pre-filter
# ---------------------------------------------------------------------------

# Keywords that strongly suggest AI consulting relevance
HIGH_SIGNAL_KEYWORDS = [
    "agent", "rag", "retrieval", "enterprise", "deploy", "production",
    "claude", "gpt", "gemini", "llama", "mistral", "frontier",
    "regulation", "compliance", "liability", "governance", "eu ai act",
    "pricing", "cost", "api", "benchmark", "eval", "latency", "context window",
    "multimodal", "reasoning", "o1", "o3", "sonnet", "haiku", "opus",
    "fine-tun", "rlhf", "alignment", "safety", "hallucin",
    "copilot", "assistant", "automation", "workflow",
]

# Keywords that suggest noise / exclusion
NOISE_KEYWORDS = [
    "consumer", "gaming", "dating", "social media", "tiktok", "instagram",
    "spotify", "netflix", "rumour", "leak", "unconfirmed", "speculate",
    "review", "hands on", "vs ", "comparison", "best of", "top 10",
]


def heuristic_score(item: dict) -> float:
    """Return a heuristic relevance score 0.0–3.0 for pre-filtering."""
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    weight = item.get("source_weight", 0.6)

    signal = sum(1 for kw in HIGH_SIGNAL_KEYWORDS if kw in text)
    noise  = sum(1 for kw in NOISE_KEYWORDS if kw in text)

    score = weight + (signal * 0.15) - (noise * 0.3)
    return max(0.0, min(3.0, score))


def cluster_by_topic(items: list[dict]) -> list[dict]:
    """
    Simple title-word clustering: if two or more items share ≥ 3 significant
    words in their title, keep only the highest-weighted one.
    """
    def sig_words(title: str) -> set[str]:
        stopwords = {"the", "a", "an", "and", "or", "in", "on", "for", "of",
                     "to", "with", "from", "is", "are", "as", "it", "its",
                     "how", "why", "what", "by", "at", "be", "this", "that"}
        words = re.findall(r"[a-z]{3,}", title.lower())
        return {w for w in words if w not in stopwords}

    clusters: list[list[dict]] = []
    used = set()

    for i, item in enumerate(items):
        if i in used:
            continue
        cluster = [item]
        words_i = sig_words(item.get("title", ""))
        for j, other in enumerate(items[i+1:], start=i+1):
            if j in used:
                continue
            words_j = sig_words(other.get("title", ""))
            if len(words_i & words_j) >= 3:
                cluster.append(other)
                used.add(j)
        used.add(i)
        clusters.append(cluster)

    # For each cluster, keep the item with the highest source weight
    result = []
    for cluster in clusters:
        best = max(cluster, key=lambda x: x.get("source_weight", 0.6))
        if len(cluster) > 1:
            best["cluster_size"] = len(cluster)
            best["cluster_titles"] = [c["title"] for c in cluster if c is not best]
        result.append(best)

    removed = len(items) - len(result)
    if removed:
        log(f"Clustering collapsed {removed} duplicate story/stories")

    return result


def heuristic_prefilter(items: list[dict]) -> list[dict]:
    """Apply heuristic scoring and keep items above a minimum threshold."""
    scored = [(heuristic_score(item), item) for item in items]
    scored.sort(key=lambda x: -x[0])

    # Keep everything above 0.4 (very low bar — just removes obvious noise)
    # but cap at MAX_CANDIDATES_FOR_MODEL to limit Haiku token use
    filtered = [item for score, item in scored if score >= 0.4]
    filtered = filtered[:MAX_CANDIDATES_FOR_MODEL]

    log(f"Heuristic pre-filter: {len(items)} → {len(filtered)} candidates")
    return filtered


# ---------------------------------------------------------------------------
# Step 4: Haiku scoring
# ---------------------------------------------------------------------------

def _load_policy() -> str:
    if POLICY_FILE.exists():
        return POLICY_FILE.read_text()
    return (
        "Score items 1–5 on: Relevance, Novelty, Actionability, Credibility. "
        "Total ≥ 10/20 = shortlist. Return JSON array."
    )


def _haiku_score_batch(items: list[dict], api_key: str) -> list[dict] | None:
    """
    Send a batch of items to Claude Haiku for consulting-relevance scoring.
    Returns a list of items with 'haiku_score' added, or None on failure.
    """
    policy = _load_policy()

    items_text = "\n\n".join(
        f"[{i}] TITLE: {item.get('title','')}\n"
        f"    SOURCE: {item.get('source_name','')} (weight={item.get('source_weight',0.6)})\n"
        f"    SUMMARY: {item.get('summary','')[:300]}"
        for i, item in enumerate(items)
    )

    prompt = (
        f"You are scoring AI news items for a weekly briefing for an independent AI consultant "
        f"who advises enterprise clients.\n\n"
        f"POLICY EXCERPT:\n{policy[:2000]}\n\n"
        f"ITEMS TO SCORE:\n{items_text}\n\n"
        f"For each item, provide a JSON object with:\n"
        f"  index: the [n] number above\n"
        f"  score: integer 0-20 (sum of Relevance+Novelty+Actionability+Credibility, each 1-5)\n"
        f"  reason: one sentence explaining the score\n\n"
        f"Respond ONLY with a JSON array. No preamble. No explanation. Just the array.\n"
        f"Example: [{{\"index\":0,\"score\":14,\"reason\":\"...\"}}, ...]"
    )

    payload = json.dumps({
        "model": HAIKU_MODEL,
        "max_tokens": 1024,
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
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        log_err(f"Haiku API request failed: {e}")
        return None

    try:
        raw_text = result["content"][0]["text"]
        # Extract JSON array from response (handle markdown code fences)
        json_match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if not json_match:
            log_err(f"Could not find JSON array in Haiku response: {raw_text[:200]}")
            return None
        scores = json.loads(json_match.group())
    except Exception as e:
        log_err(f"Failed to parse Haiku response: {e}")
        return None

    # Apply scores back to items
    score_map = {s["index"]: s for s in scores if isinstance(s, dict) and "index" in s}
    for i, item in enumerate(items):
        if i in score_map:
            item["haiku_score"] = score_map[i].get("score", 0)
            item["haiku_reason"] = score_map[i].get("reason", "")
        else:
            item["haiku_score"] = 0
            item["haiku_reason"] = "not scored"

    return items


def model_score(items: list[dict]) -> list[dict]:
    """
    Attempt Haiku scoring. Falls back to heuristic-only ranking on failure.
    """
    api_key = _anthropic_key()

    if not api_key:
        log("No ANTHROPIC_API_KEY — using heuristic-only ranking")
        for item in items:
            item["haiku_score"] = int(heuristic_score(item) * 5)
            item["haiku_reason"] = "heuristic fallback (no API key)"
        return items

    log(f"Sending {len(items)} candidates to Haiku for scoring…")
    result = _haiku_score_batch(items, api_key)

    if result is None:
        log("Haiku scoring failed — falling back to heuristic-only ranking")
        for item in items:
            item["haiku_score"] = int(heuristic_score(item) * 5)
            item["haiku_reason"] = "heuristic fallback (Haiku unavailable)"
        return items

    log("Haiku scoring complete")
    return result


# ---------------------------------------------------------------------------
# Step 5: Shortlist selection
# ---------------------------------------------------------------------------

def build_shortlist(items: list[dict], top_n: int) -> dict:
    """
    Select the top_n items. Handle the "nothing important" case explicitly.
    """
    # Sort by Haiku score descending
    items.sort(key=lambda x: x.get("haiku_score", 0), reverse=True)

    threshold = 10  # from policy
    priority_threshold = 14  # Tavily-eligible

    qualified = [i for i in items if i.get("haiku_score", 0) >= threshold]
    watch_items = [i for i in items if 7 <= i.get("haiku_score", 0) < threshold]

    if len(qualified) < NOTHING_IMPORTANT_THRESHOLD:
        log(f"Only {len(qualified)} item(s) meet threshold — quiet week")
        return {
            "quiet_week": True,
            "shortlist": qualified[:top_n],
            "watch_items": watch_items[:5],
            "all_scored": items,
        }

    shortlist = qualified[:top_n]

    # Mark Tavily-eligible items
    for item in shortlist:
        item["tavily_eligible"] = item.get("haiku_score", 0) >= priority_threshold

    log(f"Shortlist: {len(shortlist)} items ({sum(1 for i in shortlist if i.get('tavily_eligible'))} Tavily-eligible)")

    return {
        "quiet_week": False,
        "shortlist": shortlist,
        "watch_items": watch_items[:3],
        "all_scored": items,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def rank(raw_file: Path | None, top_n: int) -> dict:
    run_start = datetime.now(timezone.utc).isoformat()

    # Load raw items: aggregate all files since last briefing (decoupled from
    # seen-items.json fetch dedup) so unbriefed items are reconsidered.
    if raw_file is not None:
        items = load_raw_items(raw_file)
        source_label = str(raw_file)
    else:
        items = load_raw_items_since_last_briefing()
        source_label = "aggregated-since-last-briefing"

    if not items:
        log("No raw items to rank")
        return {
            "run_start": run_start,
            "raw_file": source_label,
            "items_loaded": 0,
            "items_shortlisted": 0,
            "quiet_week": True,
        }

    log(f"Loaded {len(items)} items ({source_label})")

    # Filter already-included (by URL hash and by topic fingerprint)
    included_hashes, included_token_sets = load_included_data()
    items = filter_already_included(items, included_hashes, included_token_sets)

    # Cluster same-story items
    items = cluster_by_topic(items)

    # Heuristic pre-filter
    candidates = heuristic_prefilter(items)

    if not candidates:
        log("No candidates after heuristic filter — quiet week")
        today = datetime.now().strftime("%Y-%m-%d")
        ranked_file = RANKED_DIR / f"{today}.json"
        result_data = {
            "quiet_week": True,
            "shortlist": [],
            "watch_items": [],
            "generated_at": run_start,
            "source_raw": str(raw_file),
        }
        _write_json(ranked_file, result_data)
        return {
            "run_start": run_start,
            "items_loaded": len(items),
            "items_after_filter": 0,
            "items_shortlisted": 0,
            "quiet_week": True,
            "ranked_file": str(ranked_file),
        }

    # Model scoring
    scored = model_score(candidates)

    # Build shortlist
    shortlist_result = build_shortlist(scored, top_n)

    # Write ranked output
    today = datetime.now().strftime("%Y-%m-%d")
    ranked_file = RANKED_DIR / f"{today}.json"
    output = {
        **shortlist_result,
        "generated_at": run_start,
        "source_raw": str(raw_file),
        "policy_version": "1.0",
    }
    _write_json(ranked_file, output)
    log(f"Ranked output written to {ranked_file}")

    return {
        "run_start": run_start,
        "raw_file": str(raw_file),
        "ranked_file": str(ranked_file),
        "items_loaded": len(items),
        "items_after_cluster": len(items),
        "items_after_heuristic": len(candidates),
        "items_shortlisted": len(shortlist_result["shortlist"]),
        "quiet_week": shortlist_result["quiet_week"],
        "haiku_used": _anthropic_key() != "",
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AI Briefing Ranker")
    p.add_argument("--raw-file", type=Path, default=None,
                   help="Path to raw items JSON (default: latest in raw/)")
    p.add_argument("--top-n", type=int, default=DEFAULT_TOP_N,
                   help=f"Max items in shortlist (default: {DEFAULT_TOP_N})")
    return p.parse_args()


def main() -> dict:
    args = parse_args()

    # When no explicit file given, pass None so rank() aggregates all raw files
    # since last briefing — decoupled from fetch dedup (seen-items.json).
    raw_file: Path | None = args.raw_file
    if raw_file is not None and not raw_file.exists():
        log_err(f"Specified raw file not found: {raw_file}")
        sys.exit(1)
    if raw_file is None and not RAW_DIR.exists():
        log_err("Raw directory not found. Run collect.py first.")
        sys.exit(1)

    log(f"Ranking (top-n={args.top_n}, {'explicit file: ' + str(raw_file) if raw_file else 'aggregating since last briefing'})")
    summary = rank(raw_file, args.top_n)

    state = load_state()
    state["rank"] = summary
    save_state(state)

    log(f"Ranking complete: {summary.get('items_shortlisted', 0)} items shortlisted "
        f"({'quiet week' if summary.get('quiet_week') else 'normal week'})")
    return summary


if __name__ == "__main__":
    main()
