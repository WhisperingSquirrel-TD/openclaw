"""
Company statutory deadline engine (Module 1)

Deterministic, auditable derivation of UK statutory accounting and tax
deadlines for a private limited company from a small set of inputs.

This module contains NO external calls and NO I/O. It is pure date logic so
that every deadline it produces can be unit-tested against the published
HMRC / Companies House rules. Treat this file as the single source of truth
for "when is X due"; everything else in the system consumes it.

RULES ENCODED (verified against GOV.UK / Companies House guidance):

  Companies House — annual accounts
    - First accounts: due 21 months after the date of incorporation.
    - Subsequent accounts: due 9 months after the Accounting Reference Date
      (ARD). (6 months for public companies — not applicable here.)
    - Default ARD: the last day of the month of the incorporation
      anniversary. First financial year runs incorporation -> first ARD.

  HMRC — Corporation Tax
    - CT payment: due 9 months + 1 day after the end of the accounting period
      (for companies with profits below the £1.5m instalments threshold).
    - CT600 filing: due 12 months after the end of the accounting period.
    - The CT accounting period cannot exceed 12 months, so a first "long"
      period (incorporation -> ARD, which can be up to ~12 months) is fine,
      but where incorporation-to-ARD exceeds 12 months HMRC splits it into
      two periods. This engine flags that split rather than guessing.

  Companies House — Confirmation Statement
    - First statement: review period is 12 months from incorporation; the
      statement is due within 14 days of the end of that review period.

  HMRC — Self Assessment (director, date only — not computed here)
    - Online return + payment: 31 January following the end of the tax year
      (tax year ends 5 April).

  VAT
    - Registration is compulsory once VAT-taxable turnover exceeds the
      registration threshold (rolling 12-month basis, or expected within the
      next 30 days). Threshold value is configurable — see config.py — because
      it changes at fiscal events.

  PAYE / RTI (conditional — only if the director takes a salary)
    - Registering as an employer must be done before the first payday.
    - Full Payment Submission (FPS) is due on or before each payday.

  NOTE ON CATO: The free joint HMRC/Companies House filing portal (CATO)
  closed on 31 March 2026. From 1 April 2026 the CT600 must be filed via
  commercial software. This engine schedules the *deadlines*; the filing
  mechanism is handled downstream (see the data-pack module).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum


class Category(str, Enum):
    """Grouping for each obligation, used for filtering and display."""

    COMPANIES_HOUSE = "Companies House"
    CORPORATION_TAX = "Corporation Tax (HMRC)"
    CONFIRMATION = "Confirmation Statement"
    VAT = "VAT (HMRC)"
    PAYE = "PAYE / RTI (HMRC)"
    SELF_ASSESSMENT = "Self Assessment (personal)"


class Severity(str, Enum):
    HARD = "hard"          # statutory deadline; penalties apply if missed
    PREP = "prep"          # internal milestone to start work
    WATCH = "watch"        # threshold to monitor, not a fixed date
    INFO = "info"          # informational / conditional


@dataclass(frozen=True)
class Deadline:
    """A single dated (or watch) obligation."""

    title: str
    category: Category
    severity: Severity
    due: date | None            # None for WATCH items with no fixed date
    note: str = ""
    prep_lead_days: int = 0     # for HARD items, how far ahead prep should begin

    def prep_start(self) -> date | None:
        if self.due is None or self.prep_lead_days == 0:
            return None
        return self.due - timedelta(days=self.prep_lead_days)


def _add_months(d: date, months: int) -> date:
    """Add calendar months to a date, clamping to the month's last day."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last))


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def default_ard(incorporation: date) -> date:
    """
    Default Accounting Reference Date: last day of the month in which the
    first anniversary of incorporation falls. E.g. incorporated 14 Jan 2026
    -> ARD 31 Jan 2027.
    """
    return _month_end(incorporation.year + 1, incorporation.month)


def first_period_end(incorporation: date, ard: date | None = None) -> date:
    """End of the first financial year (the ARD)."""
    return ard if ard is not None else default_ard(incorporation)


def tax_year_end_on_or_after(d: date) -> date:
    """The 5 April ending the tax year that contains date d."""
    boundary = date(d.year, 4, 5)
    return boundary if d <= boundary else date(d.year + 1, 4, 5)


@dataclass
class CompanyProfile:
    """
    The small set of facts the whole engine derives from.

    All dates are datetime.date. Optional fields default to None / False so the
    engine can be run with the minimum known and progressively enriched.
    """

    name: str
    incorporation: date
    trading_start: date                    # when the company began to trade
    ard: date | None = None                # None -> use default_ard()
    pre_trading_spend_from: date | None = None  # earliest pre-trade expenditure
    vat_registered: bool = False
    takes_salary: bool = False             # director on payroll -> PAYE stream
    first_payday: date | None = None       # required if takes_salary
    is_dormant_for_ct: bool = False        # trading now => normally False

    def resolved_ard(self) -> date:
        return first_period_end(self.incorporation, self.ard)

    def period_length_months(self) -> float:
        start, end = self.incorporation, self.resolved_ard()
        return (end.year - start.year) * 12 + (end.month - start.month) + (
            end.day - start.day
        ) / 30.0


def build_schedule(
    profile: CompanyProfile,
    as_of: date | None = None,
    ct_prep_lead_days: int = 60,
    accounts_prep_lead_days: int = 45,
) -> list[Deadline]:
    """
    Derive the full first-cycle statutory schedule for the company.

    Returns a list of Deadline objects sorted by due date (WATCH/undated items
    last). `as_of` is accepted for future filtering but does not alter the
    computed statutory dates.
    """
    out: list[Deadline] = []
    inc = profile.incorporation
    period_end = profile.resolved_ard()

    # --- Companies House: first annual accounts (21 months from incorporation)
    accounts_due = _add_months(inc, 21)
    out.append(
        Deadline(
            title="First annual accounts to Companies House",
            category=Category.COMPANIES_HOUSE,
            severity=Severity.HARD,
            due=accounts_due,
            prep_lead_days=accounts_prep_lead_days,
            note=(
                f"First accounts due 21 months after incorporation. "
                f"Financial year: {inc.isoformat()} to {period_end.isoformat()}. "
                "Micro-entity accounts (FRS 105) filable free via Companies "
                "House WebFiling."
            ),
        )
    )

    # --- Corporation Tax period-length guard
    period_months = profile.period_length_months()
    if period_months > 12.0:
        out.append(
            Deadline(
                title="CT period split required (first period > 12 months)",
                category=Category.CORPORATION_TAX,
                severity=Severity.INFO,
                due=None,
                note=(
                    "Incorporation-to-ARD exceeds 12 months, so HMRC will "
                    "treat this as TWO Corporation Tax accounting periods: the "
                    "first 12 months, then the remainder. Two CT600s, two "
                    "payment dates. Confirm the split before computing CT."
                ),
            )
        )

    # --- HMRC: Corporation Tax (only if not dormant for CT)
    if not profile.is_dormant_for_ct:
        ct_payment_due = _add_months(period_end, 9) + timedelta(days=1)
        ct_filing_due = _add_months(period_end, 12)
        out.append(
            Deadline(
                title="Corporation Tax payment",
                category=Category.CORPORATION_TAX,
                severity=Severity.HARD,
                due=ct_payment_due,
                prep_lead_days=ct_prep_lead_days,
                note=(
                    "CT due 9 months + 1 day after period end "
                    f"({period_end.isoformat()}). Note: payment is due BEFORE "
                    "the return-filing deadline."
                ),
            )
        )
        out.append(
            Deadline(
                title="Company Tax Return (CT600) filing",
                category=Category.CORPORATION_TAX,
                severity=Severity.HARD,
                due=ct_filing_due,
                prep_lead_days=ct_prep_lead_days,
                note=(
                    "CT600 due 12 months after period end. CATO closed "
                    "31 Mar 2026 — file via recognised commercial software."
                ),
            )
        )
    else:
        out.append(
            Deadline(
                title="Notify HMRC of dormant status",
                category=Category.CORPORATION_TAX,
                severity=Severity.INFO,
                due=None,
                note=(
                    "Marked dormant for CT. If trading has in fact begun, this "
                    "flag is wrong — trading start triggers CT obligations."
                ),
            )
        )

    # --- Companies House: first Confirmation Statement
    review_period_end = _add_months(inc, 12)
    cs_due = review_period_end + timedelta(days=14)
    out.append(
        Deadline(
            title="First Confirmation Statement",
            category=Category.CONFIRMATION,
            severity=Severity.HARD,
            due=cs_due,
            prep_lead_days=14,
            note=(
                "Review period is 12 months from incorporation; statement due "
                "within 14 days of the review-period end. £34 online."
            ),
        )
    )

    # --- HMRC: director Self Assessment (date only, not computed here)
    sa_tax_year_end = tax_year_end_on_or_after(profile.trading_start)
    sa_due = date(sa_tax_year_end.year + 1, 1, 31)
    out.append(
        Deadline(
            title="Self Assessment (online return + payment)",
            category=Category.SELF_ASSESSMENT,
            severity=Severity.PREP,
            due=sa_due,
            prep_lead_days=30,
            note=(
                "Personal return covering the tax year ending "
                f"{sa_tax_year_end.isoformat()}. NOT computed by this system "
                "(other income sources exist). SEER supplies salary/dividend "
                "figures as inputs only."
            ),
        )
    )

    # --- VAT (conditional / watch)
    if profile.vat_registered:
        out.append(
            Deadline(
                title="VAT returns (quarterly, MTD)",
                category=Category.VAT,
                severity=Severity.INFO,
                due=None,
                note=(
                    "VAT registered: returns and payments are due one calendar "
                    "month + 7 days after each VAT quarter end. Quarter stagger "
                    "depends on registration — set once known."
                ),
            )
        )
    else:
        out.append(
            Deadline(
                title="VAT registration threshold watch",
                category=Category.VAT,
                severity=Severity.WATCH,
                due=None,
                note=(
                    "Not VAT registered. Monitor rolling 12-month VAT-taxable "
                    "turnover against the registration threshold; register "
                    "within 30 days of the month in which it is crossed, or "
                    "when expected to cross within the next 30 days."
                ),
            )
        )

    # --- PAYE / RTI (conditional on taking a salary)
    if profile.takes_salary:
        if profile.first_payday is not None:
            out.append(
                Deadline(
                    title="Register as employer (before first payday)",
                    category=Category.PAYE,
                    severity=Severity.HARD,
                    due=profile.first_payday,
                    prep_lead_days=14,
                    note=(
                        "Taking a salary makes SEER an employer. Register for "
                        "PAYE before the first payday and file an FPS on or "
                        "before each payday thereafter."
                    ),
                )
            )
        out.append(
            Deadline(
                title="PAYE payment to HMRC (monthly)",
                category=Category.PAYE,
                severity=Severity.INFO,
                due=None,
                note=(
                    "PAYE/NIC due by the 22nd of the following tax month "
                    "(electronic). Single-director companies with no other "
                    "employees generally cannot claim Employment Allowance — "
                    "worth confirming the salary is worth the RTI admin."
                ),
            )
        )

    def sort_key(d: Deadline):
        return (0, d.due) if d.due is not None else (1, date.max)

    return sorted(out, key=sort_key)
