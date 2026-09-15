---
name: sharepoint
description: Read SharePoint's local mirror and submit safe, version-checked operations through the seer-finance/transport boundary.
---

# SharePoint

This skill is the agent-facing contract for the SharePoint mirror and transport
boundary. It applies to every SharePoint-backed workflow, including CRM,
expenses, finance, and receipt evidence.

## Read path

Reads do not use the write queue. Read `SHAREPOINT_INDEX.md` first, then read
the corresponding entry from:

```
~/.openclaw/workspace/sharepoint-cache/<SharePoint path>
```

The cache is a mirror, not an authority. Check its sync header and
`.manifest.json` when freshness matters. The cache poller stores canonical
`.xlsx` workbooks as their exact binary bytes; it does **not** make an
`.extracted.md` file authoritative for a workbook. Text extraction companions
are for eligible non-XLSX binary documents only. For a canonical workbook,
the approved package call is:

```python
from seer_finance.sharepoint_boundary import get_boundary

snapshot = get_boundary().read_workbook_snapshot(
    "/Expenses/Expense ledger.xlsx"
)
```

That snapshot validates the authenticated native `eTag`, version, freshness,
exact source-byte `content_sha256`, XLSX structure, and visible-table semantic
hash. Do not read a decoded Markdown representation and call it the workbook
snapshot.

## Write boundaries (mandatory)

An agent must **never open, truncate, replace, append to, or otherwise edit**
`~/.openclaw/sharepoint-queue.json`. Do not use shell redirection, `jq`, a
text editor, or a hand-written read/modify/write JSON helper for that file.

For either canonical ledger, the exact package-level public API is:

```python
boundary = get_boundary()
snapshot = boundary.read_workbook_snapshot(path)
result = boundary.write_workbook_verified(
    path,
    complete_content_base64,
    content_sha256=submitted_content_sha256,
    base_etag=snapshot["etag"],
    expected_source_sha256=snapshot["content_sha256"],
    expected_snapshot=snapshot,
    semantic_workbook_sha256=submitted_semantic_sha256,
)
```

The package boundary has `read_workbook_snapshot(...)`,
`write_workbook_verified(...)`, and `upload_receipt_verified(...)`; it does not
have a public Python `update_workbook(...)` method. The watcher adapter exposes
`update_workbook` only as a compatibility alias and accepts
`semantic_sha256` for its protocol. The package's actual semantic keyword is
`semantic_workbook_sha256`.

The writer emits a conceptual queue entry with
`operation: "update_workbook"`. That is the queue operation consumed by the
locked processor, not an API name and not permission for an agent to construct
or edit the queue file. Queue submission is not write success: wait for the
machine result and cache readback. The queue processor runs independently of
the interactive shell/TOTP gate.

For non-ledger SharePoint operations, use the installed locked producer
`sharepoint_queue_processor.enqueue_operation(operation)` with one complete
operation object. The producer takes the queue lock, de-duplicates by `id`,
and atomically publishes the request. If that producer or boundary is
unavailable, report `blocked`; never fall back to direct queue-file access.

## Operation contract

Every non-ledger operation has a unique stable `id`, an ISO-8601 UTC
`requested_at`, and a full SharePoint `path` beginning with `/`. Supported
transport operations are `create`, `update`, `append`, `move`, `upload_binary`,
and `read_binary`. Generic operations are not permitted for either canonical
ledger workbook. Use `content` for text writes and operation-specific fields
for binary/move/read operations. Do not use `allow_overwrite` for an existing
document.

The conceptual canonical workbook operation (passed to the boundary/worker,
never written by an agent to the queue file) contains:

```json
{
  "id": "seer-finance-workbook:<boundary-generated-sha256>",
  "operation": "update_workbook",
  "path": "/Finance/Finance ledger.xlsx",
  "content_base64": "<complete merged XLSX bytes>",
  "content_sha256": "<sha256 of submitted XLSX bytes>",
  "semantic_workbook_sha256": "<sha256 of visible workbook tables>",
  "semantic_sha256": "<compatible alias of the semantic hash>",
  "base_etag": "<exact authenticated native SharePoint eTag>",
  "base_version": "<exact authenticated cache version>",
  "base_content_sha256": "<sha256 of current cached XLSX>",
  "expected_source_sha256": "<same current XLSX sha256>",
  "if_match": "<same base_etag>",
  "verify_readback": true,
  "no_totp": true
}
```

The package boundary derives a stable workbook operation ID from the canonical
path, native base `eTag`, source hash, and submitted semantic hash. Agents
must not invent an ID or bypass that boundary. For `move`, include
`destination`. For `upload_binary`, include `source_path`, `content_sha256`,
and `mime_type`; preserve the original file and its hash. For `read_binary`,
omit content and use the resulting cache extraction only for supported
non-workbook binary documents.

## Optimistic concurrency and native version semantics

Before changing an existing document or workbook:

1. Read the current cached document and its manifest metadata.
2. For a canonical workbook, call
   `get_boundary().read_workbook_snapshot(...)` and retain its exact bytes,
   native `eTag`, authenticated version, and hashes.
3. Preserve the native `eTag` exactly, including quotes and spelling. It is an
   opaque SharePoint version validator. Never invent a version, increment an
   `eTag`, use a local hash as an `eTag`, or use `*`.
4. Compute `expected_source_sha256` over the exact source bytes read before the
   edit, not over a normalized or newly generated copy.
5. Merge into the existing visible tables and submit
   `content_base64`, `content_sha256`, `base_etag`,
   `expected_source_sha256`, `expected_snapshot`, and
   `semantic_workbook_sha256` through `write_workbook_verified(...)`.
   Ordinary text documents use the transport's version-checked text operation.

Both native preconditions are required for `write_workbook_verified(...)`
targeting either:

* `/Expenses/Expense ledger.xlsx`
* `/Finance/Finance ledger.xlsx`

The worker passes `base_etag` as Graph `If-Match` and checks the source hash
before writing. A successful workbook write must be read back and verified by
both binary and semantic identity. The resulting `eTag` is a new opaque
native SharePoint version; it is not a value the agent can calculate or
predict. Office package metadata may change binary identity while semantic
identity remains equal.

## Rebase, pending, and blocked outcomes

If the current `eTag` differs from `base_etag`, the current source hash differs
from `expected_source_sha256`, or Graph returns a precondition/conflict
response (HTTP 409/412 or explicit `rebase_required`), classify the operation
as `rebase_required`. Do not retry the same payload, weaken either precondition,
or overwrite the remote workbook. Keep the requested change as a pending
intent, re-read the current workbook snapshot, reconcile against that newer
source, calculate fresh binary/source/semantic hashes, and submit a new
boundary operation. If the current workbook cannot be read, leave the item
`blocked` with the exact error.

A missing result, missing/mismatched readback proof, stale/malformed cache, or
`SharePointWritePending` is not automatically a rebase: preserve it as
`pending` or `blocked` with the exact error and let the autonomous worker
resolve/retry it. Do not submit another whole-workbook rewrite while the
original operation is unresolved. Invalid payloads, unavailable producers,
unavailable boundaries, and unresolved prior mutations are `blocked`.

## Machine result proof

Inspect the approved machine result and cache readback after processing. A
canonical workbook write is complete only when all applicable fields agree:

```json
{
  "id": "seer-finance-workbook:<sha256>",
  "operation": "update_workbook",
  "path": "/Finance/Finance ledger.xlsx",
  "success": true,
  "resulting_etag": "\"{new native SharePoint eTag}\"",
  "readback_sha256": "<sha256 of exact downloaded result bytes>",
  "readback_semantic_workbook_sha256": "<sha256 of downloaded visible tables>",
  "processed_at": "2026-08-24T12:01:02Z",
  "retryable": false
}
```

The semantic readback may use the compatible keys
`readback_semantic_workbook_sha256`, `semantic_workbook_sha256`,
`semantic_sha256`, or `readback_workbook_semantic_sha256`; the value must equal
the submitted semantic hash. `resulting_etag` may be represented as `etag`.
`success: true` without a non-empty resulting native `eTag`, exact
`readback_sha256`, matching semantic readback hash, path, and `processed_at` is
not sufficient. Confirm the cache's resulting `.xlsx` bytes and manifest
before reporting success. Report the operation ID and exact
`blocked`/`pending`/`rebase_required` reason otherwise.

## Receipt proof

Receipt evidence uses the exact package API:

```python
boundary.upload_receipt_verified(
    path="/Expenses/Receipts/<source-linked-name>",
    source_ref="<mail/message/receipt source>",
    local_path="/path/to/original-receipt",
    content_sha256="<sha256 of exact local bytes>",
    mime_type="application/pdf",
)
```

This creates a conceptual `operation: "upload_binary"` request. It must not
target a canonical `.xlsx` ledger. Treat `accepted` or queued upload as
pending, not proof. Completion requires `success: true`, `status` of
`uploaded` or `exists`, the exact path, a resulting `etag`, `processed_at`,
and `readback_sha256` equal to the original local-byte hash. Retain the source
reference in the workbook even if the evidence upload is blocked.

## Canonical finance and expense boundary

The only authoritative business records in this workflow are:

* `/Expenses/Expense ledger.xlsx` — canonical expense review and expense
  evidence references.
* `/Finance/Finance ledger.xlsx` — canonical finance ledger, including
  confirmed income and posted financial movements.

Local SQLite databases, `transactions.json`, `seer-expenses.md`, local queues,
Markdown ledgers, and outcome files are migration, reconciliation, evidence,
or recovery state only. They are never alternate authorities and must not be
presented as the current ledger. A local write is not a SharePoint write and
cannot satisfy either canonical ledger's proof requirements.

## Deployment wiring

The checked-in installer:

* installs `openpyxl` from the seer-finance requirements before workbook
  services start;
* deploys the workbook semantic codec beside both `microsoft` and
  `microsoft-l1` transport entry points;
* runs the SharePoint cache poller from `microsoft` every 15 minutes;
* runs the locked queue processor from `microsoft` every minute; and
* deploys the Graph SharePoint CLI only under `microsoft-l1`, so routine
  assistant-owned processing does not require an interactive TOTP turn.

The installer also links the binary extractor for supported non-XLSX
documents. A missing dependency, cache poller, queue processor, or approved
boundary is a deployment health blocker, not permission to use a Markdown
ledger, direct queue edit, generic workbook append, or TOTP fallback.

## Safety

* Read before write; update complete content only after merging against the
  authenticated current source.
* Never silently create a second ledger or a competing finance/expense file.
* Never delete, rename, move, or change permissions unless a separately
  governed operation explicitly permits it.
* Never report a document as written from queue submission alone. Report the
  operation ID, machine proof, resulting `eTag`, readback hashes, or the exact
  pending/blocked/rebase-required reason.