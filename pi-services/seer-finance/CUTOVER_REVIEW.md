# SQLite P&L cutover review procedure

This branch does not perform a cutover. The intended canonical P&L/accounting source after approval is SQLite `finance_transactions`; legacy JSON is import/evidence only.

## Safe dry-run parity check

```bash
PYTHONPATH=. python3 -m seer_finance.ledger.compare_legacy_sqlite \
  --legacy-transactions /approved/copy/transactions.json \
  --database /approved/copy/expense-ledger.sqlite3 --json
```

It is read-only and returns non-zero on a figure discrepancy. It compares turnover, allowable expenses, capital additions, non-trading movements, taxable profit before capital allowances, and CT estimate.

## Import path

```bash
PYTHONPATH=. python3 -m seer_finance.ledger.legacy_import_cli \
  --legacy-transactions /approved/copy/transactions.json \
  --database /approved/copy/expense-ledger.sqlite3
```

Without `--apply`, this is a dry run. `--apply` is idempotent by `source_ref` and must only be used on a separately approved copy after a verified SQLite backup/restore check.

## Backup, rollback and discrepancy handling

1. Create a SQLite-consistent backup and independently restore/verify it using `backup_restore` before any approved import.
2. Run the parity comparison against copies. Any mismatch blocks cutover: preserve both inputs, export the discrepancy output, and reconcile by stable source reference.
3. Do not overwrite legacy JSON or a live SQLite database. Rollback means restoring an isolated verified SQLite copy and replaying from the recorded source watermark; it is never an in-place replacement.
4. Only after zero discrepancies, approval, and production-change controls may a separate cutover decision be considered.
