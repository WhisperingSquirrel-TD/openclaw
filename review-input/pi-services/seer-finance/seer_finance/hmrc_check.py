"""
HMRC figure staleness checker.

Purpose: before an accounting run, confirm that the fiscal figures this system
holds (in config.py) still match HMRC's currently published figures. If they
diverge, raise a loud, structured warning and STOP. The checker never rewrites
config.py — a change to a statutory figure is always a deliberate human edit,
reviewed and applied by hand. This prevents any web page, whether genuinely
updated or maliciously altered, from silently changing the numbers that feed a
statutory return.

Design and security posture:
  - Detection is automated; mutation is manual. The checker returns findings;
    it has no code path that writes to config.py.
  - Each check names an authoritative GOV.UK source URL and the specific figure
    expected. Sources are pinned to gov.uk domains; anything else is refused.
  - Network is treated as untrusted input. Fetched pages are parsed defensively:
    we search for the expected figure rather than executing or trusting page
    structure, and a fetch failure is reported as "could not verify", never as
    "unchanged".
  - The checker is offline-first: it takes a `fetcher` callable so it can be
    unit-tested deterministically and so the network layer can be swapped for
    the environment it runs in (the Pi). No network code is hard-wired here.

Intended use: run daily on the always-on host (the Pi, alongside OpenClaw).
On any finding other than "all current", it exits non-zero so the surrounding
scheduler surfaces it and the accounting run does not silently proceed on stale
figures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable
from urllib.parse import urlparse

from .config import FiscalConstants, FY_2025_26

# Only these hosts are ever fetched for verification. A source outside this set
# is a configuration error and is refused rather than fetched.
_ALLOWED_HOSTS = {"www.gov.uk", "gov.uk"}

# A fetcher takes a URL and returns the page text, or raises. Injected so the
# network layer is chosen by the caller (and mocked in tests).
Fetcher = Callable[[str], str]


class CheckStatus(str, Enum):
    CURRENT = "current"              # held figure found on the source page
    CHANGED = "changed"              # source no longer shows the held figure
    UNVERIFIABLE = "unverifiable"    # could not fetch/parse — NOT "unchanged"
    REFUSED = "refused"              # source URL failed the allow-list


@dataclass(frozen=True)
class Check:
    """One figure to verify against one authoritative source."""

    key: str                 # human name, e.g. "VAT registration threshold"
    held_value: str          # the figure we currently hold, as it appears
    source_url: str          # authoritative GOV.UK page
    # A regex whose presence on the page confirms the held figure is current.
    # Kept as an explicit pattern so the "what counts as a match" rule is
    # auditable rather than buried in fetch logic.
    confirm_pattern: str


@dataclass(frozen=True)
class Finding:
    check: Check
    status: CheckStatus
    detail: str


def _host_allowed(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return False
    return host in _ALLOWED_HOSTS


def checks_for(fc: FiscalConstants) -> list[Check]:
    """
    Build the verification checks from the held fiscal constants.

    Each held figure is paired with the GOV.UK page that publishes it and a
    pattern that must be present for the figure to count as current. Patterns
    are deliberately tolerant of thousands separators and surrounding words but
    strict on the actual number.
    """
    vat = f"{fc.vat_registration_threshold_gbp:,}"          # e.g. "90,000"
    vat_loose = str(fc.vat_registration_threshold_gbp)       # e.g. "90000"
    return [
        Check(
            key="VAT registration threshold",
            held_value=f"£{vat}",
            source_url="https://www.gov.uk/vat-registration-thresholds",
            confirm_pattern=rf"£?\s?({re.escape(vat)}|{re.escape(vat_loose)})\b",
        ),
        Check(
            key="Corporation Tax main rate",
            held_value=f"{fc.ct_main_rate:.0%}",
            source_url="https://www.gov.uk/corporation-tax-rates",
            confirm_pattern=rf"\b{int(fc.ct_main_rate*100)}\s?%",
        ),
        Check(
            key="Corporation Tax small profits rate",
            held_value=f"{fc.ct_small_profits_rate:.0%}",
            source_url="https://www.gov.uk/corporation-tax-rates",
            confirm_pattern=rf"\b{int(fc.ct_small_profits_rate*100)}\s?%",
        ),
    ]


def run_check(check: Check, fetcher: Fetcher) -> Finding:
    """Verify a single check. Never raises for network issues — reports them."""
    if not _host_allowed(check.source_url):
        return Finding(
            check, CheckStatus.REFUSED,
            f"source host not on allow-list: {check.source_url}",
        )
    try:
        page = fetcher(check.source_url)
    except Exception as exc:  # network layer is untrusted; contain all failures
        return Finding(
            check, CheckStatus.UNVERIFIABLE,
            f"could not fetch source ({type(exc).__name__}): {exc}",
        )
    if not isinstance(page, str) or not page.strip():
        return Finding(check, CheckStatus.UNVERIFIABLE, "empty response from source")

    if re.search(check.confirm_pattern, page):
        return Finding(check, CheckStatus.CURRENT,
                       f"held figure {check.held_value} present on source")
    return Finding(
        check, CheckStatus.CHANGED,
        f"held figure {check.held_value} NOT found on source — figure may have "
        f"changed. Verify {check.source_url} and update config.py by hand.",
    )


def run_all(fetcher: Fetcher, fc: FiscalConstants = FY_2025_26) -> list[Finding]:
    return [run_check(c, fetcher) for c in checks_for(fc)]


def all_current(findings: list[Finding]) -> bool:
    """True only if every check confirmed the held figure is current."""
    return all(f.status is CheckStatus.CURRENT for f in findings)
