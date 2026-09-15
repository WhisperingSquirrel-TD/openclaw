# SharePoint authority cutover review procedure

The live seer-finance boundary targets SharePoint documents
`/Expenses/Expense ledger.md` and `/Finance/Finance ledger.md`. This package does
not perform Graph operations or claim a completed cutover: queue processing and
cache readback must be independently verified before a write is accepted.
Legacy JSON and local SQLite are migration/recovery inputs only.

## Safe migration/recovery parity check

```bash
PYTHONPATH=. python3 -m seer_finance.ledger.compare_legacy_sqlite \
  --legacy-transactions /approved/copy/transactions.json \
  --database /approved/copy/expense-ledger.sqlite3 --json
```

It is read-only and returns non-zero on a figure discrepancy. It compares
turnover, allowable expenses, capital additions, non-trading movements, taxable
profit before capital allowances, and CT estimate before migration/recovery.
The SQLite copy is not the live accounting authority.

## Import path

```bash
PYTHONPATH=. python3 -m seer_finance.ledger.legacy_import_cli \
  --legacy-transactions /approved/copy/transactions.json \
  --database /approved/copy/expense-ledger.sqlite3
```

Without `--apply`, this is a dry run. `--apply` is idempotent by `source_ref` and
must only be used on a separately approved recovery/migration copy after a
verified SQLite backup/restore check. It does not make SQLite authoritative.

## Backup, rollback and discrepancy handling

1. Create a SQLite-consistent backup and independently restore/verify it using
   `backup_restore` before any approved migration or recovery import.
2. Run the parity comparison against copies. Any mismatch blocks the operation:
   preserve both inputs, export the discrepancy output, and reconcile by stable
   source reference.
3. Do not overwrite legacy JSON, SharePoint documents, or a live runtime record.
   Recovery means restoring an isolated verified SQLite copy and replaying through
   the SharePoint boundary after external queue/readback verification.
4. Treat SharePoint as authoritative only after processed-success results and
   exact cache readback have been observed for the destination document.
