# Finance ledger and P&L-source components

This directory contains source-only accounting-support components: deterministic transaction classification, profit/Corporation-Tax figure roll-ups, SharePoint-authoritative expense capture/review and finance ledger boundaries, SQLite migration/recovery tooling, and tests.

## Safety boundary

This is **not** a production deployment and does not contain live financial data. The repository intentionally excludes databases, `transactions.json`, statements, receipts, attachments, runtime state, credentials and environment files. The code does not file tax returns or provide tax advice.

## P&L/figure review

```bash
PYTHONPATH=. python3 -m seer_finance.ledger.cli --legacy-transactions examples/transactions.example.json --json --estimate-ct
```

All money is integer pence. The output provides turnover, allowable/disallowable expenditure, capital additions, non-trading movements, and profit before capital allowances.

## SharePoint authority and migration contract

Live business records target `/Expenses/Expense ledger.md` and `/Finance/Finance ledger.md`
through the Pi SharePoint queue/results/cache contract. A write is not accepted until
the queue reports processed success and the local SharePoint cache reads back the exact
submitted document. No Graph access is fabricated by this package.

SQLite is not a live authority. `ExpenseRepository`, `SqliteFinanceWriter`, and
`sqlite_loader` are retained for explicit migration, replay, and recovery only.
The migration schema's current expected version is **4**. Set
`SEER_FINANCE_DATABASE` and (where needed) `SEER_FINANCE_REPLAY`/`SEER_FINANCE_ROOT`
only for those workflows.

## Tests

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The Pi-only watcher integration test is intentionally excluded because it imports a separate runtime by absolute host path. It belongs with the watcher system, not this portable source package.

## Storage decision

SharePoint is the intended business-record authority for expenses and finance
transactions. `transactions.json` and local SQLite rows are migration/evidence or
recovery inputs, not competing P&L sources. `sharepoint_loader` reads the cached
authoritative finance document; `sqlite_loader.load_finance_transactions` remains
an explicitly selected recovery projection. This source package performs no Graph
operation and cannot claim a cutover until an external queue processor and cache
readback have succeeded.
