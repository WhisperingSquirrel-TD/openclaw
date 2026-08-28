"""Explicit one-way legacy JSON import into SQLite; never runs implicitly."""
from __future__ import annotations
import argparse
import json
from .legacy_transactions_migration import migrate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import validated legacy accounting JSON into SQLite")
    parser.add_argument("--legacy-transactions", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--apply", action="store_true", help="required: otherwise report planned operation only")
    args = parser.parse_args(argv)
    if not args.apply:
        print(json.dumps({"mode": "dry_run", "would_import": args.legacy_transactions, "database": args.database,
                          "note": "No database changed. Re-run with --apply only against an approved copy."}, indent=2))
        return 0
    print(json.dumps(migrate(transactions_path=args.legacy_transactions, database=args.database), indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
