"""
Running Corporation Tax estimate.

Answers "how much CT am I building up so far this year?" from the year-to-date
ledger. This is an ESTIMATE for management purposes, not a filed figure. Every
result carries the assumptions it rests on and the reasons it may differ from
the final return.

What it does:
  - Takes the CT summary (turnover, allowable, disallowable, capital additions)
    from the ledger.
  - Applies the Annual Investment Allowance to capital additions (100% relief
    in the period, up to the AIA cap), so qualifying equipment reduces profit.
  - Computes taxable profit, then Corporation Tax with marginal relief,
    dividing the profit limits by (associated companies + 1).

What it deliberately does NOT do:
  - It does not decide the final AIA claim, year-end adjustments, or any reliefs
    beyond the simple AIA-on-equipment model here.
  - It does not file anything.
  - It does not determine associated-company status — that is a judgement you
    confirm with an accountant; the count is an input.

All money is integer pence. Rates use Decimal for exactness. Pounds appear only
in formatted output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from ..config import FiscalConstants, FY_2025_26
from .computation import CTSummary, pounds

PENNY = Decimal("0.01")


@dataclass(frozen=True)
class CTEstimate:
    tax_year: int
    associated_companies: int
    turnover_pence: int
    allowable_pence: int
    aia_claimed_pence: int
    taxable_profit_pence: int
    effective_lower_limit_pence: int
    effective_upper_limit_pence: int
    rate_band: str                 # 'small', 'marginal', or 'main'
    estimated_ct_pence: int
    assumptions: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)


def _round_pence(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def estimate_ct(
    summary: CTSummary,
    associated_companies: int = 0,
    aia_cap_pence: int = 1_000_000_00,   # AIA annual cap: £1,000,000
    fc: FiscalConstants = FY_2025_26,
    period_fraction: Decimal = Decimal("1"),
) -> CTEstimate:
    """
    Estimate CT from a year-to-date ledger summary.

    associated_companies: number of OTHER companies associated with SEER
        (common control). The profit limits are divided by this count + 1.
    period_fraction: if the accounting period is shorter than 12 months, the
        profit limits are pro-rated. Default 1 (full year).
    """
    assumptions: list[str] = []
    caveats: list[str] = []

    # --- Annual Investment Allowance on capital additions ---
    # Simple model: qualifying equipment gets 100% relief up to the AIA cap.
    aia_claimed = min(summary.capital_additions_pence, aia_cap_pence)
    if summary.capital_additions_pence > 0:
        assumptions.append(
            f"Capital additions of {pounds(summary.capital_additions_pence)} "
            f"given 100% AIA relief ({pounds(aia_claimed)} claimed). Confirm all "
            "items qualify for AIA before filing."
        )

    # --- Taxable profit ---
    profit_before_ca = summary.taxable_profit_before_capital_allowances_pence
    taxable_profit = profit_before_ca - aia_claimed
    if taxable_profit < 0:
        taxable_profit = 0
        caveats.append(
            "Allowable costs and AIA exceed income to date: taxable profit is "
            "nil so far, so estimated CT is nil. A loss may be carried forward."
        )

    # --- Divide profit limits by (associated companies + 1), pro-rate period ---
    divisor = associated_companies + 1
    lower = _round_pence(
        Decimal(fc.ct_lower_limit_gbp * 100) / divisor * period_fraction
    )
    upper = _round_pence(
        Decimal(fc.ct_upper_limit_gbp * 100) / divisor * period_fraction
    )

    if associated_companies > 0:
        assumptions.append(
            f"{associated_companies} associated compan"
            f"{'y' if associated_companies == 1 else 'ies'} assumed: profit "
            f"limits divided by {divisor} (lower {pounds(lower)}, upper "
            f"{pounds(upper)}). Associated-company status must be confirmed with "
            "an accountant — it changes the rate."
        )
    else:
        assumptions.append(
            "No associated companies assumed. If you control other companies, "
            "they are likely associated and would REDUCE these limits, raising "
            "the effective rate. Confirm with an accountant."
        )

    # --- Apply the CT rate with marginal relief ---
    profit = Decimal(taxable_profit)
    main_rate = Decimal(str(fc.ct_main_rate))
    small_rate = Decimal(str(fc.ct_small_profits_rate))

    if taxable_profit <= lower:
        rate_band = "small"
        ct = profit * small_rate
    elif taxable_profit >= upper:
        rate_band = "main"
        ct = profit * main_rate
    else:
        rate_band = "marginal"
        # CT = main rate on profit, less marginal relief:
        # relief = fraction * (upper - profit) * (profit / augmented_profit).
        # With no distributions/FII, augmented profit = profit, so the ratio is 1.
        frac = Fraction(fc.ct_marginal_relief_fraction)
        relief = Decimal(frac.numerator) / Decimal(frac.denominator) * (
            Decimal(upper) - profit
        )
        ct = profit * main_rate - relief
        assumptions.append(
            "Marginal relief applied assuming no franked investment income "
            "(dividends received from other companies). If SEER receives such "
            "dividends, augmented profits change the relief."
        )

    estimated_ct = _round_pence(ct)

    caveats.append(
        "This is a mid-year ESTIMATE, not the final CT figure. It will change "
        "with year-end adjustments, the final AIA/capital allowances claim, and "
        "confirmation of associated-company status. Not tax advice — confirm "
        "with an accountant before relying on it or paying."
    )

    return CTEstimate(
        tax_year=fc.tax_year,
        associated_companies=associated_companies,
        turnover_pence=summary.turnover_pence,
        allowable_pence=summary.total_allowable_pence,
        aia_claimed_pence=aia_claimed,
        taxable_profit_pence=taxable_profit,
        effective_lower_limit_pence=lower,
        effective_upper_limit_pence=upper,
        rate_band=rate_band,
        estimated_ct_pence=estimated_ct,
        assumptions=assumptions,
        caveats=caveats,
    )
