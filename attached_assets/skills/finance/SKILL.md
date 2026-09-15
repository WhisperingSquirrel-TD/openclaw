---
name: finance
description: Maintain the canonical SharePoint finance workbook through the seer-finance boundary with native eTag, binary, and semantic proof.
---

# Finance

The sole authoritative finance record is the editable Excel workbook:

```
/Finance/Finance ledger.xlsx
```

Read and reconcile the current SharePoint workbook before every change. Keep
expense review in `/Expenses/Expense ledger.xlsx`; do not create a local,
Markdown, or combined finance ledger. Preserve all existing visible workbook
tables and rows.

## Public API versus queue operation (MANDATORY)

The package-level `seer_finance` boundary has no public Python
`update_workbook(...)` method. The exact direct package calls are:

```python
from seer_finance.sharepoint_boundary import get_boundary

boundary = get_boundary()
snapshot = boundary.read_workbook_snapshot("/Finance/Finance ledger.xlsx")
result = boundary.write_workbook_verified(
    "/Finance/Finance ledger.xlsx",
    content_base64,
    content_sha256=submitted_sha256,
    base_etag=snapshot["etag"],
    expected_source_sha256=snapshot["content_sha256"],
    expected_snapshot=snapshot,
    semantic_workbook_sha256=submitted_semantic_sha256,
)
```

The watcher adapter can expose `update_workbook` as a compatibility alias and
can accept the shorter `semantic_sha256` keyword. The package boundary's actual
keyword is `semantic_workbook_sha256`. The method creates a conceptual locked
queue operation with `operation: "update_workbook"`; that operation name is not
a Python call and never authorises direct edits to
`~/.openclaw/sharepoint-queue.json`.

## Workbook snapshot and write contract

Every update to `/Finance/Finance ledger.xlsx` must start from one
authenticated `read_workbook_snapshot(...)` result and pass that unchanged
`expected_snapshot` to `write_workbook_verified(...)`. Merge the financial fact
into the complete existing XLSX package and retain every visible table, sheet,
row, and source reference. The request contains:

* `path: "/Finance/Finance ledger.xlsx"`;
* `content_base64`, containing the complete merged XLSX bytes;
* `content_sha256`, the SHA-256 of those exact submitted bytes;
* `base_etag`, copied exactly from `snapshot["etag"]`;
* `expected_source_sha256`, the SHA-256 of the exact bytes in
  `snapshot["content_bytes"]`; and
* `semantic_workbook_sha256`, the visible-table semantic identity of the
  submitted workbook, independent of Office package metadata.

The conceptual queue entry also carries the authenticated `base_version`,
`verify_readback: true`, `no_totp: true`, and a boundary-generated stable
operation `id`. Do not calculate an `eTag`, use a local hash as an `eTag`, set
`*`, invent an operation ID, or weaken a missing precondition. The queue
processor accepts `semantic_sha256` as an alias for the same semantic value.

The raw workbook bytes are cached at
`~/.openclaw/workspace/sharepoint-cache/Finance/Finance ledger.xlsx`. The
`.manifest.json` record carries freshness, native eTag/version, exact-byte
`content_sha256`, and semantic hash. A Markdown extraction is not a finance
authority or write source.

## Proof and failure statuses

`BoundaryResult.accepted` only means that the boundary accepted or queued a
request. It is not proof that the books changed. Report the finance workbook as
updated only after the machine result and cache readback contain `success: true`,
the operation `id`, canonical `path`, `processed_at`, `resulting_etag` (or
`etag`), `readback_sha256`, and a matching semantic field from
`readback_semantic_workbook_sha256`, `semantic_workbook_sha256`,
`semantic_sha256`, or `readback_workbook_semantic_sha256`. Confirm that the
readback hash is the exact cached XLSX hash and that its native eTag/version is
the resulting one. Office metadata may change the binary hash while leaving
semantic identity unchanged; both proofs must still be present.

An unresolved queue result, missing proof, stale/malformed cache, or
`SharePointWritePending` response is `pending`/`blocked`, not success. Preserve
the financial fact and exact machine-readable blocker; do not submit a second
whole-workbook mutation while the first is unresolved.

Only a stale native eTag/source hash or explicit remote/Graph conflict
(HTTP 409/412 or `rebase_required`) is `rebase_required`. Do not retry its
payload. Read a fresh authenticated snapshot, preserve both versions while
merging the fact, compute fresh binary/source/semantic hashes, and submit a new
operation through `seer_finance`. Invalid input, unavailable boundary/cache, or
an unresolved prior mutation is `blocked` with the exact error; a missing proof
does not itself prove that the remote changed.

## Recovery boundary

Local SQLite, `transactions.json`, `seer-expenses.md`, migration exports and
runtime queues are migration, reconciliation, evidence, or recovery state
only. They are not finance authority, do not compete with the SharePoint
workbook, and must never be described as the current books. Never use generic
`append` or `create` for either canonical workbook, and never edit the queue
file directly.