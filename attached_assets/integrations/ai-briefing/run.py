#!/usr/bin/env python3
"""
AI Briefing Orchestrator — OpenClaw Integration
================================================

Single cron target. Runs the full pipeline: collect → rank → synthesize.
Handles errors at each step, writes run outcome to state.json.

Usage:
  python3 run.py [--no-telegram] [--no-tavily] [--lookback-days N]

Exit codes:
  0   Pipeline complete (briefing written)
  1   Fatal error (collect: all sources failed, or ranked file missing)
  2   Partial failure (collect succeeded but rank or synthesize had issues)

Logs to stdout/stderr (cron redirects these to the log file).
"""

import argparse
import json
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

STATE_DIR       = Path.home() / ".openclaw"
BRIEFING_DIR    = STATE_DIR / "ai-briefing"
STATE_FILE      = BRIEFING_DIR / "state.json"
SCRIPTS_DIR     = Path(__file__).parent
LOG_PREFIX      = "[ai-briefing/run]"


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
    except Exception:
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
# Step runner
# ---------------------------------------------------------------------------

def run_step(script: Path, extra_args: list[str], step_name: str) -> tuple[bool, str]:
    """
    Run a pipeline step. Returns (success, output_tail).
    Never raises — all exceptions are caught and returned as failures.
    """
    cmd = [sys.executable, str(script)] + extra_args
    log(f"Running {step_name}: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(SCRIPTS_DIR),
        )
        combined = (result.stdout + result.stderr).strip()
        tail = "\n".join(combined.splitlines()[-20:]) if combined else "(no output)"

        if result.returncode == 0:
            log(f"{step_name} succeeded")
            return True, tail
        else:
            log_err(f"{step_name} failed (rc={result.returncode})")
            return False, tail

    except subprocess.TimeoutExpired:
        msg = f"{step_name} timed out after 300s"
        log_err(msg)
        return False, msg
    except Exception as e:
        msg = f"{step_name} exception: {traceback.format_exc()}"
        log_err(msg)
        return False, msg


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run_pipeline(
    lookback_days: int,
    no_telegram: bool,
    no_tavily: bool,
) -> int:
    run_start = datetime.now(timezone.utc).isoformat()
    log(f"Pipeline started (lookback={lookback_days}d, "
        f"telegram={'off' if no_telegram else 'on'}, "
        f"tavily={'off' if no_tavily else 'on'})")

    state = load_state()
    state["pipeline_run_start"] = run_start
    state["pipeline_status"] = "running"
    save_state(state)

    # ── Step 1: Collect ───────────────────────────────────────────────────────
    collect_args = [f"--lookback-days={lookback_days}"]
    collect_ok, collect_out = run_step(
        SCRIPTS_DIR / "collect.py",
        collect_args,
        "collect",
    )

    if not collect_ok:
        # Distinguish config-fatal errors from transient partial failures.
        state = load_state()
        collect_state = state.get("collect", {})
        collect_error = collect_state.get("error", "")

        fatal = collect_error in ("all sources failed", "no sources loaded")

        state["pipeline_status"] = "failed"
        state["pipeline_error"] = f"collect failed: {collect_error or 'unknown'}"
        state["pipeline_end"] = datetime.now(timezone.utc).isoformat()
        save_state(state)

        if fatal:
            log_err(f"Collection failed ({collect_error}). Aborting pipeline — "
                    f"no new data to rank or synthesize.")
            return 1
        else:
            log_err("Collection step error. Attempting to continue with existing raw data.")

    # ── Step 2: Rank ──────────────────────────────────────────────────────────
    rank_ok, rank_out = run_step(
        SCRIPTS_DIR / "rank.py",
        [],
        "rank",
    )

    if not rank_ok:
        log_err("Ranking failed — cannot synthesize without a ranked file")
        state = load_state()
        state["pipeline_status"] = "partial_failure"
        state["pipeline_error"] = "rank failed"
        state["pipeline_end"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        return 2

    # ── Step 3: Synthesize ────────────────────────────────────────────────────
    # Pass the explicit ranked-file path from state so synthesize.py never
    # picks up a stale prior-week file via the "latest by date" heuristic.
    state_now = load_state()
    ranked_file_path = state_now.get("rank", {}).get("ranked_file", "")
    if not ranked_file_path or not Path(ranked_file_path).exists():
        today_ranked = BRIEFING_DIR / "ranked" / f"{datetime.now().strftime('%Y-%m-%d')}.json"
        if today_ranked.exists():
            ranked_file_path = str(today_ranked)
        else:
            log_err("No ranked file found after rank step — cannot synthesize")
            state = load_state()
            state["pipeline_status"] = "partial_failure"
            state["pipeline_error"] = "ranked file missing after rank step"
            state["pipeline_end"] = datetime.now(timezone.utc).isoformat()
            save_state(state)
            return 2

    synth_args = ["--ranked-file", ranked_file_path]
    if no_telegram:
        synth_args.append("--no-telegram")
    if no_tavily:
        synth_args.append("--no-tavily")

    synth_ok, synth_out = run_step(
        SCRIPTS_DIR / "synthesize.py",
        synth_args,
        "synthesize",
    )

    # Synthesis is resilient by design — fallback always writes a file.
    # If the script itself returns non-zero, that's a genuine error.
    if not synth_ok:
        log_err("Synthesis step returned an error. Check logs.")
        state = load_state()
        state["pipeline_status"] = "partial_failure"
        state["pipeline_error"] = "synthesize failed"
        state["pipeline_end"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        return 2

    # Verify briefing file actually exists on disk — guards against in-band
    # error paths that exit zero without writing a file.
    state_check = load_state()
    bf_path = state_check.get("synthesize", {}).get("briefing_file", "")
    if not bf_path or not Path(bf_path).exists():
        log_err(f"Synthesis reported success but briefing file not found on disk: {bf_path!r}")
        state_check["pipeline_status"] = "partial_failure"
        state_check["pipeline_error"] = "briefing file missing after synthesize"
        state_check["pipeline_end"] = datetime.now(timezone.utc).isoformat()
        save_state(state_check)
        return 2

    # ── All steps complete ────────────────────────────────────────────────────
    run_end = datetime.now(timezone.utc).isoformat()
    state = load_state()
    state["pipeline_status"] = "success"
    state["pipeline_run_start"] = run_start
    state["pipeline_end"] = run_end
    state.pop("pipeline_error", None)
    save_state(state)

    briefing_file = state.get("synthesize", {}).get("briefing_file", "unknown")
    items_included = state.get("synthesize", {}).get("items_included", 0)
    quiet_week = state.get("synthesize", {}).get("quiet_week", False)

    log(f"Pipeline complete: {briefing_file}")
    log(f"  Items included: {items_included} ({'quiet week' if quiet_week else 'normal week'})")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AI Briefing Pipeline Orchestrator")
    p.add_argument("--lookback-days", type=int, default=14,
                   help="Max age of feed items to include (default: 14)")
    p.add_argument("--no-telegram", action="store_true",
                   help="Skip Telegram ready-notification")
    p.add_argument("--no-tavily", action="store_true",
                   help="Skip Tavily article enrichment")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    rc = run_pipeline(
        lookback_days=args.lookback_days,
        no_telegram=args.no_telegram,
        no_tavily=args.no_tavily,
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
