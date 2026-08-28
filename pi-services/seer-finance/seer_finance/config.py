"""
Fiscal constants that change at Budget / fiscal events.

Keep every value that HMRC can revise in ONE place, each stamped with the tax
year it applies from and a source note, so updating the engine after a Budget
is a single deliberate edit rather than a hunt through the code.

Do NOT hard-code any of these values elsewhere. Import from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class FiscalConstants:
    """Values effective for a given tax year (year ending 5 April `tax_year`)."""

    tax_year: int
    vat_registration_threshold_gbp: int
    vat_deregistration_threshold_gbp: int
    # Corporation Tax main/small rates are informational here; CT computation
    # lives in the computation module, not the deadline engine.
    ct_small_profits_rate: float
    ct_main_rate: float
    ct_instalments_threshold_gbp: int
    # Marginal relief band: profits between the lower and upper limit are taxed
    # at the main rate less marginal relief. These limits are for ONE company
    # and are divided by (number of associated companies + 1).
    ct_lower_limit_gbp: int = 50_000
    ct_upper_limit_gbp: int = 250_000
    ct_marginal_relief_fraction: str = "3/200"  # exact fraction, as a string
    note: str = ""


# 2025/26 figures. VERIFY against GOV.UK before each first use in a new tax
# year — these are the values most likely to move.
FY_2025_26 = FiscalConstants(
    tax_year=2026,
    vat_registration_threshold_gbp=90_000,
    vat_deregistration_threshold_gbp=88_000,
    ct_small_profits_rate=0.19,
    ct_main_rate=0.25,
    ct_instalments_threshold_gbp=1_500_000,
    ct_lower_limit_gbp=50_000,
    ct_upper_limit_gbp=250_000,
    ct_marginal_relief_fraction="3/200",
    note="Confirm on GOV.UK before relying on VAT threshold and CT rates.",
)

_REGISTRY = {FY_2025_26.tax_year: FY_2025_26}


def constants_for(tax_year_end: date) -> FiscalConstants:
    """Return the fiscal constants for the tax year ending `tax_year_end`.

    Falls back to the latest known set if the exact year is not registered,
    but flags the fallback in the returned note by raising if wildly out of
    range would be safer — here we return latest and rely on the caller to
    re-verify.
    """
    year = tax_year_end.year
    if year in _REGISTRY:
        return _REGISTRY[year]
    latest = _REGISTRY[max(_REGISTRY)]
    return FiscalConstants(
        tax_year=year,
        vat_registration_threshold_gbp=latest.vat_registration_threshold_gbp,
        vat_deregistration_threshold_gbp=latest.vat_deregistration_threshold_gbp,
        ct_small_profits_rate=latest.ct_small_profits_rate,
        ct_main_rate=latest.ct_main_rate,
        ct_instalments_threshold_gbp=latest.ct_instalments_threshold_gbp,
        note=(
            f"No fiscal constants registered for tax year {year}; using "
            f"{latest.tax_year} values. VERIFY on GOV.UK before use."
        ),
    )
