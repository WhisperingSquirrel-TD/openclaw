"""Read-only pre-cutover parity check: legacy JSON versus SQLite finance ledger."""
from __future__ import annotations

import argparse
import json
import sys

from .computation import summarise
from .estimate import estimate_ct
from .loader import TransactionValidationError, load_transactions
from .sqlite_loader import SqliteLedgerLoadError, load_finance_transactions

FIELDS = ("turnover_pence", "allowable_pence", "capital_additions_pence", "non_trading_pence", "taxable_profit_before_capital_allowances_pence")


def figures(transactions):
    summary = summarise(transactions)
    estimate = estimate_ct(summary)
    result = {field: getattr(summary, field) for field in FIELDS}
    result["estimated_ct_pence"] = estimate.estimated_ct_pence
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DRY RUN ONLY: compare legacy JSON and SQLite P&L figures")
    parser.add_argument("--legacy-transactions", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        legacy, sqlite = load_transactions(args.legacy_transactions), load_finance_transactions(args.database)
    except (OSError, SqliteLedgerLoadError, TransactionValidationError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    left, right = figures(legacy), figures(sqlite)
    discrepancies = {key: {"legacy": left[key], "sqlite": right[key]} for key in left if left[key] != right[key]}
    result = {"mode": "dry_run", "legacy_transaction_count": len(legacy), "sqlite_transaction_count": len(sqlite), "discrepancies": discrepancies}
    print(json.dumps(result, indent=2) if args.json else result)
    return 0 if not discrepancies else 1


if __name__ == "__main__":
    raise SystemExit(main())
