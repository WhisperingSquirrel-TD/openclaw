"""
Transaction ledger schema for a limited company.

One company, one pot of income and expenditure (personal training and
consultancy combined). The purpose of this module is to classify each
transaction the way the Corporation Tax computation needs, so that raw
transaction data becomes correct CT600 figures.

Design decisions:
  - Money is held as integer PENCE throughout. Never use floats for money:
    binary floating point cannot represent most decimal amounts exactly and
    errors accumulate. All arithmetic is exact integer arithmetic; formatting
    to pounds happens only at display time.
  - Each transaction carries a `category` from a controlled vocabulary. The
    category implies a DEFAULT tax treatment (the accountant knowledge), which
    an explicit `tax_treatment` on the transaction may override for edge cases.
  - Amounts are always stored as positive magnitudes; `direction` distinguishes
    income from expenditure. This avoids sign-convention bugs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Direction(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"


class TaxTreatment(str, Enum):
    """How a transaction is treated in the Corporation Tax computation."""

    ALLOWABLE = "allowable"        # deductible revenue expense
    DISALLOWABLE = "disallowable"  # added back; not deductible
    CAPITAL = "capital"            # goes through capital allowances / AIA
    INCOME = "income"              # turnover
    NON_TRADING = "non_trading"    # e.g. director's loan repayment, dividend out


class Category(str, Enum):
    """
    Controlled vocabulary. OpenClaw assigns one of these per transaction; the
    ledger derives the default tax treatment from it. Keep this list small and
    stable — every value maps deliberately to a CT treatment below.
    """

    # Income
    SALES = "sales"                        # PT + consultancy turnover

    # Allowable revenue expenses
    SOFTWARE = "software"
    SUBSCRIPTIONS = "subscriptions"
    PROFESSIONAL_FEES = "professional_fees"    # accountant, legal
    INSURANCE = "insurance"
    TRAVEL = "travel"
    TRAINING = "training"                       # CPD relevant to the trade
    OFFICE_COSTS = "office_costs"
    PHONE_INTERNET = "phone_internet"
    BANK_CHARGES = "bank_charges"
    MARKETING = "marketing"
    STOCK_CONSUMABLES = "stock_consumables"
    STAFF_COSTS = "staff_costs"                 # salary/employer NI when applicable
    USE_OF_HOME = "use_of_home"
    PENSION = "pension"                         # employer pension contribution

    # Commonly disallowable
    CLIENT_ENTERTAINMENT = "client_entertainment"  # disallowable
    GIFTS = "gifts"                                # generally disallowable
    FINES_PENALTIES = "fines_penalties"            # disallowable
    DEPRECIATION = "depreciation"                  # added back

    # Capital
    EQUIPMENT = "equipment"                        # gym kit, laptops -> AIA

    # Non-trading / drawings
    DIVIDEND = "dividend"                          # distribution, not an expense
    DIRECTORS_LOAN = "directors_loan"
    CORPORATION_TAX = "corporation_tax_payment"    # not deductible
    VAT_PAYMENT = "vat_payment"                     # not a P&L item

    OTHER = "other"                                # forces manual review


# Default tax treatment per category. This encodes the HMRC treatment so
# OpenClaw only needs to pick a plausible category; the ledger applies the
# correct CT handling. Any transaction may override via its own tax_treatment.
DEFAULT_TREATMENT: dict[Category, TaxTreatment] = {
    Category.SALES: TaxTreatment.INCOME,

    Category.SOFTWARE: TaxTreatment.ALLOWABLE,
    Category.SUBSCRIPTIONS: TaxTreatment.ALLOWABLE,
    Category.PROFESSIONAL_FEES: TaxTreatment.ALLOWABLE,
    Category.INSURANCE: TaxTreatment.ALLOWABLE,
    Category.TRAVEL: TaxTreatment.ALLOWABLE,
    Category.TRAINING: TaxTreatment.ALLOWABLE,
    Category.OFFICE_COSTS: TaxTreatment.ALLOWABLE,
    Category.PHONE_INTERNET: TaxTreatment.ALLOWABLE,
    Category.BANK_CHARGES: TaxTreatment.ALLOWABLE,
    Category.MARKETING: TaxTreatment.ALLOWABLE,
    Category.STOCK_CONSUMABLES: TaxTreatment.ALLOWABLE,
    Category.STAFF_COSTS: TaxTreatment.ALLOWABLE,
    Category.USE_OF_HOME: TaxTreatment.ALLOWABLE,
    Category.PENSION: TaxTreatment.ALLOWABLE,

    Category.CLIENT_ENTERTAINMENT: TaxTreatment.DISALLOWABLE,
    Category.GIFTS: TaxTreatment.DISALLOWABLE,
    Category.FINES_PENALTIES: TaxTreatment.DISALLOWABLE,
    Category.DEPRECIATION: TaxTreatment.DISALLOWABLE,

    Category.EQUIPMENT: TaxTreatment.CAPITAL,

    Category.DIVIDEND: TaxTreatment.NON_TRADING,
    Category.DIRECTORS_LOAN: TaxTreatment.NON_TRADING,
    Category.CORPORATION_TAX: TaxTreatment.NON_TRADING,
    Category.VAT_PAYMENT: TaxTreatment.NON_TRADING,

    Category.OTHER: TaxTreatment.DISALLOWABLE,  # safe default; forces review
}


@dataclass(frozen=True)
class Transaction:
    """A single classified transaction. Amount is integer pence, positive."""

    txn_id: str
    date: str                 # ISO YYYY-MM-DD
    direction: Direction
    amount_pence: int         # positive magnitude, in pence
    description: str
    counterparty: str
    category: Category
    pre_trading: bool = False
    tax_treatment: TaxTreatment | None = None  # override; None = category default
    source_ref: str = ""      # link/reference to invoice or receipt

    def effective_treatment(self) -> TaxTreatment:
        if self.tax_treatment is not None:
            return self.tax_treatment
        return DEFAULT_TREATMENT[self.category]
