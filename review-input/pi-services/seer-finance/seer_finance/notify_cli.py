"""
Daily deadline-notification runner — OpenClaw calls this once a day via cron.

Emits today's alerts as JSON on stdout for OpenClaw to turn into a message, and
sets an exit code so cron/OpenClaw can decide whether to send anything:

    0  nothing to report today  -> OpenClaw stays quiet
    1  alerts present           -> OpenClaw sends the message(s)
    2  error (e.g. bad profile) -> OpenClaw should surface the failure

Usage (absolute path to the profile, since cron has no working directory):
    python3 -m seer_finance.notify_cli /path/to/profile.json
    python3 -m seer_finance.notify_cli /path/to/profile.json --text   # human form
"""

from __future__ import annotations

import argparse
import json
import sys

from .cli import load_profile
from .notify import alerts_for


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SEER daily deadline alerts")
    ap.add_argument("profile", help="absolute path to profile.json")
    ap.add_argument("--text", action="store_true",
                    help="human-readable output instead of JSON")
    args = ap.parse_args(argv)

    try:
        profile = load_profile(args.profile)
    except Exception as exc:  # noqa: BLE001 - report any load failure to OpenClaw
        print(f"error: {exc}", file=sys.stderr)
        return 2

    alerts = alerts_for(profile)

    if args.text:
        if not alerts:
            print("No deadline alerts today.")
        else:
            print(f"{len(alerts)} deadline alert(s):\n")
            for a in alerts:
                print(f"  [{a.urgency.value.upper()}] {a.message}")
    else:
        print(json.dumps({
            "alert_count": len(alerts),
            "alerts": [
                {
                    "title": a.title,
                    "due": a.due.isoformat(),
                    "days_until": a.days_until,
                    "urgency": a.urgency.value,
                    "message": a.message,
                }
                for a in alerts
            ],
        }, indent=2))

    return 1 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
