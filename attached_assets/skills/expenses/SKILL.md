---
name: expenses
description: Capture and review expenses in the canonical SharePoint expense ledger using the version-checked SharePoint producer contract.
---

# Expenses

The sole authoritative expense record is:

```
/Expenses/Expense ledger.md
```

Read the current SharePoint cache and native item `eTag` before proposing a
change. Preserve source references, receipt evidence and unresolved fields in
that document. Do not create a second expense ledger.

## Write route

Never edit `~/.openclaw/sharepoint-queue.json` directly. Submit one complete
operation object to the locked
`sharepoint_queue_processor.enqueue_operation(operation)` producer. Include a
unique operation ID, full path, complete merged document content,
`requested_at`, `base_etag`, and `expected_source_sha256` (the SHA-256 of the
exact current source bytes read before the merge). Queue submission is not
proof that the expense was recorded.

For a canonical ledger update or append, both `base_etag` and
`expected_source_sha256` are mandatory. The queue processor uses the eTag as
the native SharePoint `If-Match` version check and verifies the resulting
read-back hash. Never invent, increment, or replace a SharePoint eTag with a
local hash.

## Proof and conflicts

Accept an expense as recorded only after the machine result contains
`success: true`, `resulting_etag`, `readback_sha256`, `processed_at`, and the
operation ID/path, and the SharePoint cache reads back the submitted document.
If the base eTag/source hash is stale, or any conflict/read-back proof is
missing, classify the result as `rebase_required`. Re-read the current
document and eTag, merge the pending expense without losing either version,
compute a new source hash, and enqueue a new operation ID. Never retry a stale
payload or overwrite the remote ledger.

## Legacy data

Local SQLite rows, `transactions.json`, `seer-expenses.md`, receipt queues and
other local state are migration, reconciliation, evidence, or recovery inputs
only. They can be compared or replayed into the SharePoint ledger with source
identity preserved, but they are not authoritative and do not prove capture.
The finance authority is `/Finance/Finance ledger.md`; do not route an expense
to any other finance or expense document.