"""
Command-line entry point for the ledger.

Loads a validated transaction file and prints the Corporation Tax figure
summary. Thin wrapper over the library so it stays testable.

Usage:
    python -m seer_finance.ledger.cli transactions.json
    python -m seer_finance.ledger.cli transactions.json --json
"""

from __future__ import annotations

import argparse
import json
import sys

from .computation import pounds, summarise
from .loader import TransactionValidationError, load_transactions


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SEER ledger — CT figure summary")
    ap.add_argument("transactions", help="path to transactions JSON")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument(
        "--estimate-ct", action="store_true",
        help="also print a running Corporation Tax estimate",
    )
    ap.add_argument(
        "--associated-companies", type=int, default=0, metavar="N",
        help="number of OTHER companies associated with SEER (common control); "
             "divides the CT profit limits by N+1",
    )
    args = ap.parse_args(argv)

    try:
        txns = load_transactions(args.transactions)
    except (OSError, TransactionValidationError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    s = summarise(txns)

    if args.estimate_ct or args.json:
        from .estimate import estimate_ct
        est = estimate_ct(s, associated_companies=args.associated_companies)
    else:
        est = None

    if args.json:
        out = {
            "transactions": len(txns),
            "turnover_pence": s.turnover_pence,
            "allowable_pence": s.allowable_pence,
            "pre_trading_allowable_pence": s.pre_trading_allowable_pence,
            "total_allowable_pence": s.total_allowable_pence,
            "disallowable_pence": s.disallowable_pence,
            "capital_additions_pence": s.capital_additions_pence,
            "non_trading_pence": s.non_trading_pence,
            "taxable_profit_before_capital_allowances_pence":
                s.taxable_profit_before_capital_allowances_pence,
            "review_needed": s.review_needed,
        }
        if est is not None:
            out["ct_estimate"] = {
                "tax_year": est.tax_year,
                "associated_companies": est.associated_companies,
                "aia_claimed_pence": est.aia_claimed_pence,
                "taxable_profit_pence": est.taxable_profit_pence,
                "rate_band": est.rate_band,
                "estimated_ct_pence": est.estimated_ct_pence,
                "assumptions": est.assumptions,
                "caveats": est.caveats,
            }
        print(json.dumps(out, indent=2))
        return 0

    print(f"\nSEER ledger summary — {len(txns)} transactions")
    print("=" * 52)
    print(f"  Turnover                          {pounds(s.turnover_pence):>14}")
    print(f"  Allowable expenses (in-period)    {pounds(s.allowable_pence):>14}")
    print(f"  Pre-trading allowable             {pounds(s.pre_trading_allowable_pence):>14}")
    print(f"  Disallowable (added back)         {pounds(s.disallowable_pence):>14}")
    print(f"  Capital additions (AIA/CAs)       {pounds(s.capital_additions_pence):>14}")
    print(f"  Non-trading (dividends etc.)      {pounds(s.non_trading_pence):>14}")
    print("-" * 52)
    print(f"  Taxable profit before cap. allow. "
          f"{pounds(s.taxable_profit_before_capital_allowances_pence):>14}")
    if s.review_needed:
        print("\n  REVIEW NEEDED:")
        for r in s.review_needed:
            print(f"    - {r}")
    print("\n  Note: figures only. Capital allowances/AIA, the CT rate, and")
    print("  filing are handled downstream (HMRC-recognised software).")

    if est is not None:
        print("\n" + "=" * 52)
        print("  RUNNING CORPORATION TAX ESTIMATE (year to date)")
        print("=" * 52)
        print(f"  AIA claimed on equipment          {pounds(est.aia_claimed_pence):>14}")
        print(f"  Taxable profit (after AIA)        {pounds(est.taxable_profit_pence):>14}")
        print(f"  Rate band                         {est.rate_band:>14}")
        print(f"  Estimated CT so far               {pounds(est.estimated_ct_pence):>14}")
        print("\n  Assumptions:")
        for a in est.assumptions:
            print(f"    - {a}")
        print("\n  IMPORTANT:")
        for c in est.caveats:
            print(f"    - {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
