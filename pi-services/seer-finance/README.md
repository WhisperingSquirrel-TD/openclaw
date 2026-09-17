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

Live business records target the visible, editable Excel workbooks
`/Expenses/Expense ledger.xlsx` and `/Finance/Finance ledger.xlsx` through the Pi
SharePoint queue/results/cache contract. Markdown is a migration input only, never
the authority.  Expense workbooks expose Expenses, Events, Collisions, and
Evidence tables; finance workbooks expose a Transactions table.  Every field is
represented in a visible table, including a visible type marker so nulls, empty
strings, booleans, and integer pence cannot be silently changed by Excel.

The binary transport schema for an `update_workbook` queue entry is:

```json
{
  "id": "seer-finance-workbook:<sha256>",
  "operation": "update_workbook",
  "path": "/Finance/Finance ledger.xlsx",
  "content_base64": "<base64 of exact XLSX bytes>",
  "content_sha256": "<sha256 of decoded content_base64>",
  "semantic_workbook_sha256": "<hash of decoded visible tables>",
  "semantic_sha256": "<same visible-table hash used by the Pi processor>",
  "base_etag": "<authenticated cache etag>",
  "base_version": "<authenticated cache version>",
  "base_content_sha256": "<sha256 of current cached XLSX>",
  "expected_source_sha256": "<same current cached XLSX sha256>",
  "if_match": "<same base_etag>",
  "verify_readback": true,
  "required_result_fields": [
    "path", "success", "processed_at", "resulting_etag|etag",
    "readback_sha256",
    "readback_semantic_workbook_sha256|semantic_workbook_sha256|semantic_sha256"
  ],
  "no_totp": true
}
```

`content_sha256` and `readback_sha256` are hashes of exact XLSX bytes.
`semantic_workbook_sha256` is calculated from visible table values and is the
proof used when Office rewrites ZIP/XML metadata. A write is not accepted until
the queue reports processed success and the local cache reads back binary and
semantic proof. No Graph access is fabricated by this package.

Repository mutations decode one authenticated cache snapshot and carry that
snapshot's `etag`, version, and exact-byte hash through `write_workbook`; they
never reread a newer cache entry and silently rebase a whole-workbook rewrite.
The queue processor rejects a stale base. Repeated captures and transaction
retries are semantic no-ops when no business facts changed, and operation IDs
use the semantic identity while the journal retains the exact submitted bytes.
Generated packages are deterministic.

Automated updates modify the original workbook package in place. Existing table
styles, widths, comments, and data validations are retained. Openpyxl output is
used only for the edited worksheet/table members; every other source ZIP member
is copied unchanged, including custom XML, relationships, content types, and
other package metadata. A normal edit from a blank/null value infers a safe
scalar type without requiring the operator to edit the adjacent marker. Formula
cells are rejected because this source-only package cannot safely evaluate them.

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
transactions. Structured Markdown, `transactions.json`, historical Excel, and
local SQLite rows are migration/evidence or recovery inputs, not competing P&L
sources. To build reviewed local workbooks without touching SharePoint:

```bash
PYTHONPATH=. python3 -m seer_finance.ledger.workbook_migration \
  --expense-markdown old-expenses.md \
  --finance-markdown old-finance.md \
  --expense-output "Expense ledger.xlsx" \
  --finance-output "Finance ledger.xlsx" --apply
```

`sharepoint_loader` reads the cached authoritative finance workbook;
`sqlite_loader.load_finance_transactions` remains an explicitly selected
recovery projection. This source package performs no Graph operation and cannot
claim a cutover until an external queue processor and cache readback have
succeeded.
