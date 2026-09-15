"""
Runner for the HMRC staleness checker — intended to run daily on the Pi.

Exit codes (so the surrounding scheduler can act):
    0  all figures current
    3  one or more figures CHANGED — accounting run must not proceed on stale data
    4  one or more figures UNVERIFIABLE or source REFUSED — human should check

The network fetcher is defined here, in the runner, so the pure checker module
stays offline and testable. The fetcher enforces:
  - HTTPS only
  - a short timeout (a hung fetch must not hang the daily job)
  - a capped read size (an untrusted endpoint must not exhaust memory)
  - no redirects to non-gov.uk hosts
"""

from __future__ import annotations

import sys
from urllib.parse import urlparse

from .config import FY_2025_26
from .hmrc_check import CheckStatus, run_all

_TIMEOUT_SECONDS = 15
_MAX_BYTES = 2_000_000  # 2 MB cap on any single page read
_ALLOWED_HOSTS = {"www.gov.uk", "gov.uk"}


def _fetch(url: str) -> str:
    """Minimal, defensive HTTPS fetcher for gov.uk pages."""
    import urllib.request

    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
        raise ValueError(f"refusing to fetch non-gov.uk or non-HTTPS URL: {url}")

    req = urllib.request.Request(url, headers={"User-Agent": "seer-finance-check"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:  # noqa: S310
        # Re-check the final URL after any redirect: must still be gov.uk.
        final_host = urlparse(resp.geturl()).hostname
        if final_host not in _ALLOWED_HOSTS:
            raise ValueError(f"redirected off gov.uk to {final_host}")
        raw = resp.read(_MAX_BYTES)
    return raw.decode("utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    findings = run_all(_fetch, FY_2025_26)

    print("\nHMRC figure staleness check")
    print("=" * 60)
    worst = 0
    for f in findings:
        marker = {
            CheckStatus.CURRENT: "OK   ",
            CheckStatus.CHANGED: "STOP ",
            CheckStatus.UNVERIFIABLE: "CHECK",
            CheckStatus.REFUSED: "CHECK",
        }[f.status]
        print(f"  [{marker}] {f.check.key}: {f.check.held_value}")
        if f.status is not CheckStatus.CURRENT:
            print(f"           {f.detail}")
        if f.status is CheckStatus.CHANGED:
            worst = max(worst, 3)
        elif f.status in (CheckStatus.UNVERIFIABLE, CheckStatus.REFUSED):
            worst = max(worst, 4)

    print("-" * 60)
    if worst == 0:
        print("  All held figures confirmed current. Safe to proceed.")
    elif worst == 3:
        print("  A figure has CHANGED. Do NOT run accounts on the current "
              "config.\n  Verify the source pages and update config.py by hand, "
              "then re-run.")
    else:
        print("  A figure could not be verified. Check the source pages before "
              "relying on the held figures.")
    return worst


if __name__ == "__main__":
    sys.exit(main())
