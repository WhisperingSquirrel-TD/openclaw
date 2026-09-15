---
name: finance
description: Maintain the canonical SharePoint finance ledger with native eTag/source-hash concurrency and machine proof.
---

# Finance

The sole authoritative finance record is:

```
/Finance/Finance ledger.md
```

Read and reconcile the current SharePoint document before every change. Keep
expense review in `/Expenses/Expense ledger.md`; do not create a local or
combined finance ledger.

## Locked producer contract

Agents must never directly open, truncate, replace, or edit
`~/.openclaw/sharepoint-queue.json`. Submit a complete operation to
`sharepoint_queue_processor.enqueue_operation(operation)`, which owns the
queue lock, atomic publication, and operation-ID idempotency.

Every `update` or `append` to `/Finance/Finance ledger.md` must include:

* a unique operation ID and `requested_at`;
* `base_etag`, copied exactly from the current native SharePoint item;
* `expected_source_sha256`, computed from the exact current source bytes; and
* the complete merged content.

Do not calculate an eTag, use a local hash as an eTag, or weaken a missing
precondition. A successful operation must provide machine proof with
`success`, `resulting_etag`, `readback_sha256`, `processed_at`, and the
operation ID/path. Confirm the cache read-back before reporting the ledger
updated.

## Rebase-required flow

An eTag mismatch, source-hash mismatch, Graph precondition conflict, or
missing/mismatched read-back proof is `rebase_required`, not a retryable
overwrite. Re-read the current SharePoint ledger and native eTag, merge the
pending financial fact, calculate a new source hash, and enqueue a new ID
through the locked producer. Preserve both source versions and surface an
exact `blocked` error if the current ledger cannot be read.

## Recovery boundary

Local SQLite, `transactions.json`, `seer-expenses.md`, migration exports and
runtime queues are migration, reconciliation, evidence, or recovery state
only. They are not finance authority, do not compete with the SharePoint
ledger, and must never be described as the current books.