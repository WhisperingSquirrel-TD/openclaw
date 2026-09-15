"""
Command-line entry point for the deadline engine.

Reads a company profile from a JSON file and prints the derived statutory
schedule. Kept deliberately thin — all logic lives in deadlines.py so it stays
testable. Designed to be callable by an OpenClaw skill (parse the JSON output
with --json) or by a human at the terminal.

Usage:
    python -m seer_finance.cli profile.json
    python -m seer_finance.cli profile.json --json
    python -m seer_finance.cli profile.json --upcoming 90
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta

from .deadlines import CompanyProfile, build_schedule


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def load_profile(path: str) -> CompanyProfile:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    required = {"name", "incorporation", "trading_start"}
    missing = required - raw.keys()
    if missing:
        raise ValueError(f"profile missing required fields: {sorted(missing)}")

    return CompanyProfile(
        name=raw["name"],
        incorporation=_parse_date(raw["incorporation"]),
        trading_start=_parse_date(raw["trading_start"]),
        ard=_parse_date(raw.get("ard")),
        pre_trading_spend_from=_parse_date(raw.get("pre_trading_spend_from")),
        vat_registered=bool(raw.get("vat_registered", False)),
        takes_salary=bool(raw.get("takes_salary", False)),
        first_payday=_parse_date(raw.get("first_payday")),
        is_dormant_for_ct=bool(raw.get("is_dormant_for_ct", False)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SEER statutory deadline engine")
    parser.add_argument("profile", help="path to profile JSON")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--upcoming",
        type=int,
        default=None,
        metavar="DAYS",
        help="only show items due (or prep starting) within DAYS from today",
    )
    args = parser.parse_args(argv)

    try:
        profile = load_profile(args.profile)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    schedule = build_schedule(profile)

    if args.upcoming is not None:
        horizon = date.today() + timedelta(days=args.upcoming)
        schedule = [
            d
            for d in schedule
            if (d.due is not None and d.due <= horizon)
            or (d.prep_start() is not None and d.prep_start() <= horizon)
        ]

    if args.json:
        payload = [
            {
                "title": d.title,
                "category": d.category.value,
                "severity": d.severity.value,
                "due": d.due.isoformat() if d.due else None,
                "prep_start": d.prep_start().isoformat() if d.prep_start() else None,
                "note": d.note,
            }
            for d in schedule
        ]
        print(json.dumps(payload, indent=2))
        return 0

    print(f"\nStatutory schedule — {profile.name}")
    print(f"Incorporated {profile.incorporation.isoformat()} | "
          f"trading from {profile.trading_start.isoformat()} | "
          f"ARD {profile.resolved_ard().isoformat()}\n")
    for d in schedule:
        due = d.due.isoformat() if d.due else "(watch/undated)"
        print(f"  {due:>16}  [{d.severity.value:5}] {d.title}")
        if d.prep_start():
            print(f"  {'':>16}          start prep: {d.prep_start().isoformat()}")
        if d.note:
            print(f"  {'':>16}          {d.note}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
