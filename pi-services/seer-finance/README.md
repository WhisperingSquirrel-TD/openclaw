# Finance ledger and P&L-source components

This directory contains source-only accounting-support components: deterministic transaction classification, profit/Corporation-Tax figure roll-ups, expense-capture and review primitives, SQLite schema migrations, and tests.

## Safety boundary

This is **not** a production deployment and does not contain live financial data. The repository intentionally excludes databases, `transactions.json`, statements, receipts, attachments, runtime state, credentials and environment files. The code does not file tax returns or provide tax advice.

## P&L/figure review

```bash
PYTHONPATH=. python3 -m seer_finance.ledger.cli --legacy-transactions examples/transactions.example.json --json --estimate-ct
```

All money is integer pence. The output provides turnover, allowable/disallowable expenditure, capital additions, non-trading movements, and profit before capital allowances.

## Database contract

The SQLite expense ledger migrates itself via `schema_migrations`. Current expected migration version: **4**. Set `SEER_FINANCE_DATABASE` and (where needed) `SEER_FINANCE_REPLAY`/`SEER_FINANCE_ROOT` for a non-default runtime location. Defaults are generic `/var/lib/seer-finance` paths, not a live Pi location.

## Tests

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The Pi-only watcher integration test is intentionally excluded because it imports a separate runtime by absolute host path. It belongs with the watcher system, not this portable source package.

## Proposed integration decision (review only)

SQLite `finance_transactions` should become the canonical accounting/P&L input after an approved cutover. It is populated exactly once through the reviewed-expense bridge; `transactions.json` remains legacy import/evidence only, not a competing P&L source. `sqlite_loader.load_finance_transactions` is a read-only deterministic projection from the immutable SQLite rows. This branch performs no cutover, migration or production database action.
