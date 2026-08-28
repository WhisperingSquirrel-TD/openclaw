"""P&L/CT figure summary from one explicitly selected ledger input."""
from __future__ import annotations

import argparse
import json
import sys

from .computation import pounds, summarise
from .loader import TransactionValidationError, load_transactions
from .sqlite_loader import SqliteLedgerLoadError, load_finance_transactions


def _render(transactions, *, as_json: bool, estimate: bool, associated_companies: int) -> int:
    summary = summarise(transactions)
    ct = None
    if estimate or as_json:
        from .estimate import estimate_ct
        ct = estimate_ct(summary, associated_companies=associated_companies)
    if as_json:
        output = {
            "transactions": len(transactions), "turnover_pence": summary.turnover_pence,
            "allowable_pence": summary.allowable_pence,
            "pre_trading_allowable_pence": summary.pre_trading_allowable_pence,
            "total_allowable_pence": summary.total_allowable_pence,
            "disallowable_pence": summary.disallowable_pence,
            "capital_additions_pence": summary.capital_additions_pence,
            "non_trading_pence": summary.non_trading_pence,
            "taxable_profit_before_capital_allowances_pence": summary.taxable_profit_before_capital_allowances_pence,
            "review_needed": summary.review_needed,
        }
        if ct:
            output["ct_estimate"] = {"tax_year": ct.tax_year, "associated_companies": ct.associated_companies,
                "aia_claimed_pence": ct.aia_claimed_pence, "taxable_profit_pence": ct.taxable_profit_pence,
                "rate_band": ct.rate_band, "estimated_ct_pence": ct.estimated_ct_pence,
                "assumptions": ct.assumptions, "caveats": ct.caveats}
        print(json.dumps(output, indent=2))
        return 0
    print(f"\nP&L/CT figure summary — {len(transactions)} transactions")
    print(f"  Turnover {pounds(summary.turnover_pence)}")
    print(f"  Allowable expenses {pounds(summary.allowable_pence)}")
    print(f"  Capital additions {pounds(summary.capital_additions_pence)}")
    print(f"  Non-trading {pounds(summary.non_trading_pence)}")
    print(f"  Taxable profit before capital allowances {pounds(summary.taxable_profit_before_capital_allowances_pence)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P&L/CT figures from one explicitly selected ledger input")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--database", metavar="PATH", help="canonical SQLite finance ledger (read-only)")
    source.add_argument("--legacy-transactions", metavar="PATH", help="LEGACY IMPORT/EVIDENCE JSON; not authoritative after cutover")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--estimate-ct", action="store_true")
    parser.add_argument("--associated-companies", type=int, default=0, metavar="N")
    args = parser.parse_args(argv)
    try:
        transactions = load_finance_transactions(args.database) if args.database else load_transactions(args.legacy_transactions)
    except (OSError, SqliteLedgerLoadError, TransactionValidationError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return _render(transactions, as_json=args.json, estimate=args.estimate_ct,
                   associated_companies=args.associated_companies)


if __name__ == "__main__":
    raise SystemExit(main())
