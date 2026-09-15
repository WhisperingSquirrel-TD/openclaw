---
name: sharepoint
description: Read SharePoint's local mirror and submit safe, version-checked document operations through the locked queue producer.
---

# SharePoint

This skill is the agent-facing contract for the SharePoint mirror and queue.
It applies to every SharePoint-backed workflow, including CRM, expenses and
finance.

## Read path

Reads do not use the write queue. Read `SHAREPOINT_INDEX.md` first, then read
the corresponding file from:

```
~/.openclaw/workspace/sharepoint-cache/<SharePoint path>
```

The cache is a mirror, not an authority. Check its sync header and
`.manifest.json` when freshness matters. Binary documents have an
`.extracted.md` companion. If a binary needs an on-demand extraction, submit a
`read_binary` operation through the producer contract below and then read the
resulting cache file.

## Write boundary (mandatory)

An agent must **never open, truncate, replace, append to, or otherwise edit**
`~/.openclaw/sharepoint-queue.json`. Do not use shell redirection, `jq`, a
text editor, or a hand-written read/modify/write JSON helper for that file.
There is one producer boundary:

```
sharepoint_queue_processor.enqueue_operation(operation)
```

Use the installed, locked producer (or the fixed service wrapper that exposes
that producer) with one complete operation object. The producer takes the
queue lock, reads the current queue, de-duplicates by `id`, and atomically
publishes the new queue. A producer returning `false` means that the operation
ID was already queued; it is not permission to create a second ID and retry
blindly. If the producer is unavailable, report `blocked` and preserve the
operation for the owning service; do not fall back to direct queue-file access.

The queue processor is the writer. It runs independently of the agent's
interactive shell/TOTP gate. Queue submission is not write success: wait for
the machine result proof and cache read-back.

## Operation contract

Every operation has a unique stable `id`, an ISO-8601 UTC `requested_at`, and
the full SharePoint `path` beginning with `/`. Supported operations are
`create`, `update`, `append`, `move`, `upload_binary`, and `read_binary`.
Use `content` for text writes and the operation-specific fields for the others.
Do not use `allow_overwrite` for an existing document.

Example producer payload (the object is passed to `enqueue_operation`; it is
not written to the queue file by the agent):

```json
{
  "id": "sp-finance-2026-08-24-001",
  "operation": "update",
  "path": "/Finance/Finance ledger.md",
  "content": "<complete merged ledger content>",
  "base_etag": "\"{SharePoint eTag read from the current item}\"",
  "expected_source_sha256": "<sha256 of the exact current cached source bytes>",
  "requested_at": "2026-08-24T12:00:00Z",
  "delivery": "finance-ledger"
}
```

For `move`, include `destination`. For `upload_binary`, include
`source_path` and `mime_type`; preserve the original file and its hash. For
`read_binary`, omit `content`.

## Optimistic concurrency and native version semantics

Before changing an existing document:

1. Read the current cached document and its manifest metadata.
2. Obtain the current SharePoint item `eTag` through the approved reader
   route. An eTag is an opaque native SharePoint version validator; preserve
   its quotes and exact spelling. Never invent a version, increment an eTag,
   use a local hash as an eTag, or use `*`.
3. Compute `expected_source_sha256` over the exact source bytes read before the
   edit (not over a normalised or newly generated copy).
4. Merge the requested change into that source and submit both
   `base_etag` and `expected_source_sha256`.

Both preconditions are required for `update` and `append` operations targeting
either canonical ledger:

* `/Expenses/Expense ledger.md`
* `/Finance/Finance ledger.md`

The processor passes `base_etag` as Graph `If-Match` and checks the source hash
before writing. A successful write must be read back and hash-verified. The
resulting eTag is a new opaque native SharePoint version; it is not a value the
agent may calculate or predict.

## Rebase-required flow

If the current eTag differs from `base_etag`, the current source hash differs
from `expected_source_sha256`, Graph returns a precondition/conflict response,
or the write/read-back proof is missing, treat the operation as:
`rebase_required`.

Do not retry the same payload, weaken either precondition, overwrite the
remote document, or claim success. Keep the requested change as a pending
intent, re-read the current SharePoint document/eTag, reconcile the change
against that newer source, compute a new source hash, create a new operation
ID, and enqueue the rebased operation through `enqueue_operation`. If the
current document cannot be read, leave the item `blocked` with the exact
error.

## Machine result proof

After processing, inspect the machine result record in
`~/.openclaw/sharepoint-queue-results.json` and the human-readable
`~/.openclaw/workspace/SHAREPOINT_RESULT.md`. A write is complete only when
the record has all applicable fields:

```json
{
  "id": "sp-finance-2026-08-24-001",
  "operation": "update",
  "path": "/Finance/Finance ledger.md",
  "success": true,
  "resulting_etag": "\"{new native SharePoint eTag}\"",
  "readback_sha256": "<sha256 of exact downloaded result bytes>",
  "processed_at": "2026-08-24T12:01:02Z",
  "retryable": false,
  "delivery": "finance-ledger"
}
```

The processor's `SP_WRITE_PROOF` is evidence only when it contains the
resulting native eTag and read-back SHA-256, and those fields are copied into
the result record. `success: true` without `resulting_etag` and
`readback_sha256` is not sufficient for a canonical ledger. A failed result
must preserve the exact error and identify `rebase_required` when applicable.

## Canonical finance and expense boundary

The only authoritative business records in this workflow are:

* `/Expenses/Expense ledger.md` — canonical expense review and expense
  evidence references.
* `/Finance/Finance ledger.md` — canonical finance ledger, including confirmed
  income and posted financial movements.

Local SQLite databases, `transactions.json`, `seer-expenses.md`, local queues,
and outcome files are migration, reconciliation, evidence, or recovery state
only. They are never alternate authorities and must not be presented as the
current ledger. A local write is not a SharePoint write and cannot satisfy
either canonical ledger's proof requirements.

## Safety

* Read before write; update complete content only after merging against the
  current source.
* Never silently create a second ledger or a competing finance/expense file.
* Never delete, rename, move, or change permissions unless a separately
  governed operation explicitly permits it.
* Never report a document as written from queue submission alone. Report the
  operation ID, machine proof, resulting eTag, read-back hash, or the exact
  blocked/rebase-required reason.