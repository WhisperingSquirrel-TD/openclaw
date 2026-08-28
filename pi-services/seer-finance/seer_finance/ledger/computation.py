"""
Corporation Tax figure roll-up.

Aggregates validated transactions into the summary figures a micro-entity CT
computation needs. This is deliberately a computation of FIGURES, not a filed
return: it produces turnover, allowable expenses, the disallowable add-backs,
capital additions (for capital allowances / AIA), and the resulting taxable
trading profit before capital allowances.

It does NOT compute the tax due (that needs the CT rate, AIA claim decisions,
and any adjustments) and it does NOT file anything. Those are downstream and,
for a company this size, belong in HMRC-recognised software.

Pre-trading expenditure: costs flagged `pre_trading` are, under the standard
rule, treated as incurred on the first day of trading and are allowable in the
first period (provided they would have been allowable had the company been
trading). They are reported separately here so the first-period computation and
the audit trail make the treatment explicit.

All money is integer pence; pounds appear only in formatted output.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schema import Direction, TaxTreatment, Transaction


@dataclass
class CTSummary:
    turnover_pence: int = 0
    allowable_pence: int = 0                 # excludes pre-trading (shown apart)
    pre_trading_allowable_pence: int = 0
    disallowable_pence: int = 0
    capital_additions_pence: int = 0
    non_trading_pence: int = 0
    # Buckets for transparency / review
    by_category_pence: dict[str, int] = field(default_factory=dict)
    review_needed: list[str] = field(default_factory=list)

    @property
    def total_allowable_pence(self) -> int:
        return self.allowable_pence + self.pre_trading_allowable_pence

    @property
    def taxable_profit_before_capital_allowances_pence(self) -> int:
        """Turnover less allowable revenue expenses (incl. pre-trading).

        Capital additions are NOT subtracted here — they are relieved via
        capital allowances / AIA, computed separately. Disallowable items are
        excluded from relief by construction (never added to allowable).
        """
        return self.turnover_pence - self.total_allowable_pence


def summarise(transactions: list[Transaction]) -> CTSummary:
    s = CTSummary()
    for t in transactions:
        treatment = t.effective_treatment()
        s.by_category_pence[t.category.value] = (
            s.by_category_pence.get(t.category.value, 0) + t.amount_pence
        )

        if treatment is TaxTreatment.INCOME:
            if t.direction is not Direction.INCOME:
                s.review_needed.append(
                    f"{t.txn_id}: income treatment but direction={t.direction.value}"
                )
            s.turnover_pence += t.amount_pence

        elif treatment is TaxTreatment.ALLOWABLE:
            if t.pre_trading:
                s.pre_trading_allowable_pence += t.amount_pence
            else:
                s.allowable_pence += t.amount_pence

        elif treatment is TaxTreatment.DISALLOWABLE:
            s.disallowable_pence += t.amount_pence
            if t.category.value == "other":
                s.review_needed.append(
                    f"{t.txn_id}: category 'other' — classify before filing"
                )

        elif treatment is TaxTreatment.CAPITAL:
            s.capital_additions_pence += t.amount_pence

        elif treatment is TaxTreatment.NON_TRADING:
            s.non_trading_pence += t.amount_pence

    return s


def pounds(pence: int) -> str:
    """Format integer pence as a pounds string. Display only."""
    sign = "-" if pence < 0 else ""
    p = abs(pence)
    return f"{sign}£{p // 100:,}.{p % 100:02d}"
