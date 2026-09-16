---
name: expenses
description: Capture and review expenses in the canonical SharePoint expense workbook through the seer-finance boundary.
---

# Expenses

The sole authoritative expense record is the editable Excel workbook:

```
/Expenses/Expense ledger.xlsx
```

Read the current SharePoint cache workbook and its manifest/native item `eTag`
before proposing a change. Preserve source references, receipt evidence and
unresolved fields in the existing visible Excel tables. Do not create a second
expense ledger or a Markdown substitute. Workbook table structure, sheet names,
and existing rows must survive the edit.

## Public API and queue-operation distinction (MANDATORY)

The package-level public `seer_finance` boundary does **not** expose a Python
method named `update_workbook(...)`. The exact workbook methods are:

```python
from seer_finance.sharepoint_boundary import get_boundary

boundary = get_boundary()
snapshot = boundary.read_workbook_snapshot("/Expenses/Expense ledger.xlsx")
result = boundary.write_workbook_verified(
    "/Expenses/Expense ledger.xlsx",
    content_base64,
    content_sha256=submitted_sha256,
    base_etag=snapshot["etag"],
    expected_source_sha256=snapshot["content_sha256"],
    expected_snapshot=snapshot,
    semantic_workbook_sha256=submitted_semantic_sha256,
)
```

`read_workbook_snapshot(...)`, `write_workbook_verified(...)`, and
`upload_receipt_verified(...)` are the public package calls. The public
workbook writer's semantic keyword is `semantic_workbook_sha256`; the queue
and transport schema also carries the compatible aliases
`semantic_workbook_sha256` and `semantic_sha256`. The watcher adapter may
expose `update_workbook` as a compatibility alias and may accept
`semantic_sha256`, but that alias is not a method in the package boundary.

The writer creates a conceptual queue request whose
`operation: "update_workbook"` is consumed by the locked queue processor. This
operation name is not permission to construct or edit
`~/.openclaw/sharepoint-queue.json`. Agents must never open, truncate, replace,
append to, or otherwise edit that file, and must not call generic SharePoint
`append` or `create` for a canonical workbook. The boundary owns operation
identity, queue locking, idempotency, table-preserving workbook encoding, and
remote readback.

## Owner chat route

For an owner-initiated receipt capture, L1 uses the fixed
`expense_sharepoint` tool, not `exec`, a generic file tool, or a generic
SharePoint tool. It has exactly three no-TOTP actions:

This route is supported only on the verified default Pi service profile:
`HOME=/home/tomdean88`, `OPENCLAW_HOME` unset or `/home/tomdean88`, and
`OPENCLAW_STATE_DIR=/home/tomdean88/.openclaw`. It intentionally fails closed
with `unsupported_state_layout` for custom/alternate profiles because the
installed SharePoint queue and cache workers use this same fixed layout. Do not
attempt to work around that result with shell, direct queue edits, or another
SharePoint tool.

* `read_expense_workbook` reads only `/Expenses/Expense ledger.xlsx` and
  returns bounded, paginated visible expense rows, matching evidence/status
  events, and authenticated metadata (`eTag`, version, sync timestamp and
  hashes). It never returns raw XLSX bytes or Base64 and does not authorize a
  raw workbook replacement from chat. Use `page` (zero-based) and `pageSize`
  (1–50) when more rows are needed.
* `capture_expense` merges only source-linked, validated expense facts into
  the visible canonical expense table using the existing
  `SharePointExpenseRepository`. It always fixes the source surface to
  `owner_chat`; it cannot choose a workbook, queue, or remote destination.
  Its only tool fact keys are `sourceTimestamp`, `observedTimestamp`,
  `supplier`, `amountPence`, `currency`, `expenseDate`, `category`,
  `evidenceRef`, `evidenceState`, `settlementState`, `financeLedgerRef`, and
  `validationResult`. It returns the canonical `observed_timestamp` and
  `finance_ledger_ref` where recorded. Do not invent a `line_items` field: the current
  canonical workbook schema has no visible item-level table, so preserve the
  original receipt as evidence and record only supported, observed facts.
* `upload_expense_receipt` accepts only an inbound OpenClaw media path. The
  bridge validates the regular file, computes its SHA-256 itself, derives MIME
  from the allowed extension, and writes only to the content-addressed path
  `/Expenses/Receipt evidence/<sha256>.<extension>`; do not supply a hash,
  MIME type, or destination name.

This narrow route cannot send email/messages, execute commands, read arbitrary
files, or choose another SharePoint path. It reports `complete: false` for an
accepted queue operation until the queue processor has produced verified
binary/semantic readback; “accepted” or “queued” is not a saved expense. A
blocked/rebase result, conflicting repeat capture, incoming-field mismatch, or
unresolved collision is `accepted: false` and never complete.

## Workbook snapshot and mutation contract

This is the internal finance repository/queue-worker contract, not an
`expense_sharepoint` owner-chat action. The owner route cannot receive raw
workbook bytes, Base64, hashes, or a workbook-write action.

Every canonical mutation must be based on one authenticated
`read_workbook_snapshot(...)` result for the current workbook. Preserve the
snapshot unchanged while merging the complete workbook, and pass its exact
`expected_snapshot` to `write_workbook_verified(...)`. The submitted request
contains:

* `path: "/Expenses/Expense ledger.xlsx"`;
* `content_base64`: the complete merged XLSX bytes, not a fragment or decoded
  JSON payload;
* `content_sha256`: SHA-256 of those exact submitted bytes;
* `base_etag`: the opaque native SharePoint `eTag` from `snapshot["etag"]`;
* `expected_source_sha256`: SHA-256 of the exact current source bytes from
  `snapshot["content_bytes"]`; and
* `semantic_workbook_sha256`: the visible-table semantic identity of the
  submitted workbook, excluding Office ZIP/XML metadata.

The conceptual queue payload includes `operation: "update_workbook"`, the
boundary-generated stable operation `id`, `base_version` from the authenticated
snapshot, `verify_readback: true`, and `no_totp: true`. Do not invent an
operation ID, calculate an `eTag`, use a local hash as an `eTag`, or weaken a
missing precondition. `content_sha256` and the semantic hash are different
proofs: Office may rewrite package metadata while preserving visible ledger
identity.

The cache stores the raw `.xlsx` bytes at
`~/.openclaw/workspace/sharepoint-cache/Expenses/Expense ledger.xlsx`; its
`.manifest.json` carries the native `eTag`, version, freshness, exact-byte
hash, and semantic hash. A Markdown extraction is not an authoritative
workbook source. `read_workbook_snapshot(...)` validates the manifest, freshness,
exact-byte hash, XLSX structure, and semantic hash before a write is allowed.

## Proof and failure statuses

Accept an expense as recorded only after the machine result and cache readback
prove all of the following: `success: true`, the operation `id`, canonical
`path`, `processed_at`, `resulting_etag` (or `etag`), `readback_sha256`, and a
matching semantic field
`readback_semantic_workbook_sha256`, `semantic_workbook_sha256`,
`semantic_sha256`, or `readback_workbook_semantic_sha256`. Confirm that the
cache has the resulting native `eTag`/version and that its exact bytes hash to
`readback_sha256`. The readback binary hash may differ from
`content_sha256` when Office rewrites package metadata; its semantic hash must
equal the submitted semantic hash.

`BoundaryResult.accepted` means that the boundary accepted or queued the
operation; it is not remote write success. `verified`/`complete`, the machine
result, and cache readback are the completion proof. A pending result, missing
proof, missing/stale cache readback, or a `SharePointWritePending` response is
not capture proof: preserve the candidate as `pending` or `blocked` with the
exact machine-readable error and let the autonomous worker retry. Do not submit
a second whole-workbook mutation while the first operation is unresolved.

Only a stale native `eTag`/source hash or an explicit remote/Graph conflict
(HTTP 409/412 or `rebase_required`) is a `rebase_required` outcome. Do not retry
that stale payload. Re-read a fresh authenticated snapshot, merge the pending
expense without losing either version, compute fresh binary/source/semantic
hashes, and submit a new operation through `seer_finance`. Invalid payloads,
an unavailable/malformed cache, an unavailable boundary, or an unresolved
prior mutation are `blocked` with their exact errors; they are not evidence to
overwrite the workbook. A missing readback proof remains pending/blocked until
the operation is resolved or an explicit conflict is returned.

## Receipt-evidence route

Receipt binaries are evidence, not a second ledger. When binary retention is
required, call the exact public method
`boundary.upload_receipt_verified(path=..., source_ref=..., local_path=...,
content_sha256=..., mime_type=...)`. It submits the conceptual
`operation: "upload_binary"` through the locked transport with
`verify_readback: true` and `no_totp: true`; it must not target either
canonical `.xlsx` ledger. Accept receipt retention only when its result has
`success: true`, `status: "uploaded"` or `"exists"`, the exact canonical path,
a resulting `etag`, `processed_at`, and `readback_sha256` equal to the hash of
the local bytes. `accepted` or a queued `upload_binary` is pending, not proof.
Keep the source reference in the workbook row even when the evidence upload is
blocked.

## Legacy data

Local SQLite rows, `transactions.json`, `seer-expenses.md`, receipt queues and
other local state are migration, reconciliation, evidence, or recovery inputs
only. They can be compared or replayed into the SharePoint workbook with source
identity preserved, but they are not authoritative and do not prove capture.
The finance authority is `/Finance/Finance ledger.xlsx`; do not route an
expense to any other finance or expense document.

## Retained workflow guidance

The following workflow guidance applies only where it does not conflict with
the Excel workbook authority, the `seer_finance` boundary, the
version-precondition rules, and the binary/semantic/readback proof rules above.

## Position in the broader managed-item model

Expenses are one **owning workflow** beneath the broader inbound/outbound
managed-item system. The first question for any email, message or event is not
"is this an expense?" but:

- **is this a thing that needs management?**

If yes, one possible route is `EXPENSE`. This skill governs what happens after
an item has been assessed as expense-relevant or expense-shaped.

## Business reader/writer boundary (MANDATORY)

The business expense reader/writer is the established `seer_finance` XLSX
boundary. Read `/Expenses/Expense ledger.xlsx` with
`get_boundary().read_workbook_snapshot(...)`, preserve its authenticated
snapshot, and submit the complete merged workbook with
`get_boundary().write_workbook_verified(...)`. The conceptual operation
consumed by the worker is `operation: "update_workbook"`; it is not a public
Python `update_workbook(...)` call and is never a queue-file editing
instruction.

Do not substitute a direct local-file write, a direct SharePoint mutation, a
chat-shell command, a queue-file edit, a generic append/create call, or an
imagined REST/API endpoint. If an integration detail is not stated by this
skill or the live owning service, inspect that declared service contract rather
than inventing one. A receipt reader or inbox mirror is an input reader, not a
second expense writer.

## Autonomous no-TOTP invariant (MANDATORY)

The expense watcher, capture/review, rectification/enrichment worker, workbook
writer and finance-validation/reconciliation path are autonomous services.
They **must never require Tom to provide TOTP** for routine capture,
preservation, classification, review-state display, enrichment, validation,
reconciliation, or health checks.

- The runtime must use its own least-privilege service access and durable
  source-linked state; it must not depend on an L1 chat turn or an interactive
  approval window.
- If a dependent reader, workbook cache, `seer_finance` boundary, or other
  service fails, preserve the candidate as `blocked` with the exact
  machine-readable failure in the monitored/review state. Do not ask Tom for
  TOTP as a fallback.
- TOTP is permitted only for an explicitly user-authorised exceptional
  privileged change outside the normal expense operating path, such as
  host-level service installation or credential rotation. It is never a
  prerequisite for processing an expense candidate already in a monitored
  surface.
- Every integration or live-acceptance test for this system must prove the
  source → capture/review → validation path with no interactive approval.

### Chat-side gate diagnosis (MANDATORY)

**Trigger:** an assistant sees an expense signal or reports that a reader or
writer is gated, blocked, or needs approval.

**Required mechanism:** first read this invariant, `SYSTEM_MAP.md`, and the
live owning service/state; then resolve the declared non-gated route all the
way to its concrete invocation contract (the `seer_finance` workbook boundary,
  the exact `write_workbook_verified(...)` call and its conceptual
  `operation: "update_workbook"` fields, its worker/consumer, and the
canonical workbook readback proof). Attempt that route before considering any
shell/exec path. A chat-shell execution gate, or inability to use arbitrary
`exec`, is never evidence that routine expense processing requires TOTP.

**Route-discovery receipt:** before saying a capture/write route is unavailable,
name: (1) the exact governing skill read, (2) the non-gated route identifier,
(3) its concrete input contract, (4) its runtime consumer, and (5) the
workbook binary/semantic/remote readback that would prove success. If any
element is unknown, discovery is incomplete—inspect the declared route's
implementation or contract rather than substituting a familiar command or
asking Tom for TOTP.

**Fail-closed outcome:** if the autonomous route truly fails, preserve the
exact candidate as `blocked` with its machine-readable service error and
surface the health/review state. Do not ask Tom to unlock ordinary reading or
writing. Ask for approval only when the requested work is a separately
privileged system change, and name that change.

## Preservation-first data invariant (MANDATORY)

For expense capture, rectification, workbook migration and reconciliation,
data loss is worse than duplication. Preserve every source/evidence row and
conflicting value; only an exact replay may be represented idempotently. A
non-identical collision or ambiguous duplicate must remain as a separately
auditable `needs_review`/`blocked` outcome with both references—never be
deleted, overwritten, or silently merged. Legacy files become read-only
archive evidence only after row-count/checksum reconciliation proves that
every item has either a workbook destination or an explicit retained-review
state. This is a migration rule, not an alternative operating ledger.

## Canonical workbook backup invariant (MANDATORY)

The production canonical expense workbook must be included in the established
code-and-files backup cadence, retention and restore test. Use the established
workbook-consistent backup process and retain a dated manifest with the
workbook checksum, workbook/schema version where available, and source
watermark. Surface a missed or failed backup as an expense-system health
blocker. Do not place a workbook copy in an untracked runtime location or
treat a repository commit as a substitute for a backup.

## Mirror timestamp and Telegram-evidence invariant (MANDATORY)

A mirror `source_timestamp` is untrusted evidence, not safe operational
control data. The expense watcher must retain the raw value but validate it
before using it for queue ordering, display, or state: malformed or materially
future timestamps use the watcher observation time and carry an explicit
invalid status. A central `EXPENSE` flag on a Telegram conversation is
insufficient by itself; it needs concrete transactional evidence (for example a
monetary value, receipt, invoice, order, charge/payment, purchase, renewal,
subscription, refund, or reimbursement) before an unresolved workbook row is
created. A downgraded non-financial event remains traceable in monitored/source
evidence as `not_needed`; it is not silently deleted.

## Automatic Expense Email Processing (MANDATORY)

### Cross-inbox sweep rule (MANDATORY)

When checking recent expenses or when any one expense email is found, do not
stop at the current inbox. Sweep **all relevant expense inbox surfaces** in
the same pass:

- `GMAIL_INBOX.md`
- `ASSISTANT_INBOX.md`
- `MICROSOFT_INBOX.md`
- and, when relevant, the matching external/secondary feed if the expense may
  not yet be present in the trusted view

Classify every recent expense-shaped email/signal into the managed-item
seriousness model with the exact expense outcome preserved underneath it:

- `processed` (for example logged in the workbook)
- `closed` (for example duplicate already represented and fully satisfied)
- `blocked` (for example pending with blocker)
- `not_needed`

Do not finish the expense pass until all relevant visible surfaces have been
checked.

### Feed-completeness fail-closed rule (MANDATORY)

If asked whether recent expense emails were processed, check the `Last
updated:` timestamps on the inbox feed files before claiming coverage. If any
feed is stale, Tom says there are newer emails than the feed shows, or Tom
provides screenshot/browser evidence of an expense email not present in the
feeds, treat the sweep as **incomplete**.

Concrete mechanism:

- read the inbox feed timestamps;
- compare them against the claimed or visible missed-email timing;
- if the feed predates the evidence or does not show the shown message,
  classify the item as `blocked` with blocker detail
  `feed gap / not yet visible in markdown`; and
- do **not** say the system processed "recent ones properly" until that gap is
  resolved.

### Recent-mirror supplier sweep rule (MANDATORY)

When Tom says there should be a newer expense email in "the email mirror" or
challenges whether a newer supplier email was missed, run a supplier-targeted
sweep across **all mirrored inbox surfaces**, not only the first mailbox
previously inspected.

Concrete mechanism:

- identify the supplier or receipt family from Tom's challenge, such as
  `GitHub`, `Replit`, or `Microsoft`;
- read the newest relevant external/trusted mirror files:
  `GMAIL_EXTERNAL.md`, `MICROSOFT_EXTERNAL.md`, and `ASSISTANT_EXTERNAL.md`,
  plus trusted inbox mirrors where relevant;
- search for the supplier/receipt subject family and compare timestamps so the
  newest visible matching email can be named; and
- reconcile that exact newest visible item against the matching visible row or
  source reference in `/Expenses/Expense ledger.xlsx`.

If the newest visible item is absent from the workbook, answer `seen but not
fully processed` rather than implying capture from an older matching row.

### Email-landed trigger rule (MANDATORY)

If any inbox check, heartbeat, sent-items review, or manual email pass
encounters a plausible expense-related email, that sighting itself is the
trigger to act. Do not wait for Tom to later ask about expenses.

Required action chain:

1. inspect the email through the approved autonomous reader route;
2. use the service's fixed least-privilege reader and the `seer_finance`
   workbook writer; never substitute a chat-shell gate for either route;
3. if the reader, attachment download, extraction, or workbook writer fails,
   classify the item as **blocked** with the exact service failure and preserve
   it for autonomous retry; and
4. classify the item as `processed` / `blocked` / `closed` / `not_needed` with
   the exact supporting expense outcome before finishing the email pass.

### Trusted-inbox closure-proof rule (MANDATORY)

For expense-shaped emails in `ASSISTANT_INBOX.md`, `MICROSOFT_INBOX.md`, or
`GMAIL_INBOX.md`, inbox visibility is only the **arrival signal**, not proof of
processing.

Before claiming that a trusted-inbox expense email was handled, prove one of
these outcomes in the same working pass:

- a matching row or source-linked unresolved row was added/updated in the
  visible tables of `/Expenses/Expense ledger.xlsx` and the canonical
  readback proof is available;
- the item is a duplicate already represented in the workbook;
- the item was preserved as pending/blocked with the exact blocker in the
  workbook/review state; or
- the item was explicitly judged `not_needed` with a reason because it is
  truly non-expense.

Before reporting an item as captured, complete and read back:
**source identity → exact canonical workbook row → expense state → evidence
state → follow-up/blocker**. If the row is absent, classify the item as
pending with blocker and correct the workbook through `seer_finance` before
replying.

If Tom asks "did you get/process the newer expense email?" and the inbox
contains it but no matching workbook row or explicit pending/blocked outcome
exists, answer: **seen but not yet processed**. Even after logging, do not
imply the item is `closed` unless the owning expense workflow has finished the
required downstream steps.

### Newest-invoice same-pass rule (MANDATORY)

When a trusted inbox shows a newly landed supplier invoice/receipt email for a
recurring vendor already present in the workbook, do not treat older rows for
that supplier as evidence that the new one was handled.

Concrete mechanism:

- extract the newest visible invoice/receipt identifiers from the trusted inbox
  entry itself: supplier, invoice number/reference, and landed date;
- search the workbook's visible rows for that exact invoice/reference, not just
  the supplier name;
- if the exact invoice/reference is absent, merge the new row immediately
  through `seer_finance`, or preserve it in the workbook as pending/blocked
  with the exact blocker; and
- update `ACTIONED.md` only after the specific invoice/reference has a matching
  handled outcome.

A new inbox item such as `Your Microsoft invoice G168579299 is ready` is not
handled merely because older Microsoft invoices exist. The exact invoice
number must exist in the workbook or in an explicit pending/blocked outcome.

### No-gap overnight invoice rule (MANDATORY)

A newly landed trusted-inbox expense email must be captured on the first pass
that reads that feed, even if the dedicated expense watcher has not run, is
disabled, or another broad inbox cron has not fired.

Trigger = any process, skill, or manual check that reads
`MICROSOFT_INBOX.md`, `GMAIL_INBOX.md`, or `ASSISTANT_INBOX.md`. On that same
pass, scan the newest trusted-inbox items for expense-source patterns and
perform the exact-invoice check above against the workbook. If missing, create
the row through the `seer_finance` workbook mutation; do not defer it to a
later generic inbox watch.

### Trusted reader route

When an expense-source email appears in a trusted inbox, immediately process
it automatically without TOTP:

1. extract its message ID from the inbox markdown;
2. call the correct existing trusted reader:
   - for `ASSISTANT_INBOX.md`, use the trusted email reader with
     `--account assistant --download-attachments`;
   - for `MICROSOFT_INBOX.md`, use the trusted email reader with
     `--account microsoft --download-attachments`; and
   - for `GMAIL_INBOX.md`, use the trusted Gmail reader with
     `--download-attachments`;
3. parse the JSON response for subject, received date, amount, receipt/invoice
   numbers, and downloaded attachments;
4. merge the complete known details into the appropriate visible Excel table
    through the `seer_finance` `write_workbook_verified(...)` contract; and
5. preserve a receipt-evidence reference in that workbook row. If a binary
   retention route is available, use that already-governed route; never create
   a Markdown ledger or use a generic append operation as a substitute.

**Expense-source patterns to match:**

- subject contains: "receipt from Anthropic" | "receipt from Replit" | "OpenAI
  API Invoice" | "Your OpenAI API account has been funded" | "Your Microsoft
  invoice";
- sender: `invoice+statements@mail.anthropic.com` |
  `noreply@billing.replit.com` | `noreply@tm.openai.com` |
  `microsoft-noreply@microsoft.com`.

**OpenAI top-up rule (MANDATORY):** Treat OpenAI "account funded" / credit
top-up emails as expense signals in the same way as OpenAI invoice emails. If
the exact invoice document is not yet visible, still merge a pending expense
signal into the workbook with the date, visible amount, source channel, and
blocker rather than leaving it uncaptured.

**Amount extraction patterns:**

- Anthropic HTML: look for a `<span>` with `font-size:36px` containing
  `$XX.XX`;
- OpenAI HTML: look for `<b>$X.XX</b> USD` in body text;
- Replit HTML: similar to Anthropic (Stripe-based); and
- extract both subtotal and total, preferring total.

### Mirror-layer guarantee rule (MANDATORY)

The guarantee that an expense signal will be handled must live at the
mirror/watch layer, not only inside the full-body reader route. If an item
appears in a mirrored inbox, sent-items view, WhatsApp recent feed, or similar
monitored surface and looks expense-shaped, that appearance itself must create
one of these managed-item outcomes in the same pass:

- `processed`
- `closed`
- `blocked`
- `not_needed`

The exact expense outcome still needs to be named beneath that state, such as
logged in the workbook, duplicate already represented, or pending with an
exact blocker. Do not let a suspicious item disappear merely because an
extractor, trusted reader, or richer route failed.

**Automatic trigger path:**

- Pi-native watcher code:
  `/home/tomdean88/openclaw/pi-services/expense-intake-watcher/watcher.py`;
- runtime state/log source:
  `~/.openclaw/runtime/expense-intake-watcher/state.json` and
  `~/.openclaw/runtime/expense-intake-watcher/watcher.log`;
- watches new items across `GMAIL_INBOX.md`, `ASSISTANT_INBOX.md`, and
  `MICROSOFT_INBOX.md`;
- reads new expense-shaped mail through the trusted reader routes; and
- submits canonical workbook changes through the public `seer_finance` XLSX
  boundary.

Do not diagnose freshness from the repository copy under
`~/pi-services/expense-intake-watcher/`; that location is not the live state
source.

### External inbox emails

If an expense email appears in `MICROSOFT_EXTERNAL.md` or
`GMAIL_EXTERNAL.md` while its body is hidden, preserve it immediately as a
source-linked `blocked` candidate in the monitored/review state and route it
into the autonomous enrichment path. Do not demand chat TOTP as a substitute
for that worker.

The blocker must name the actual missing evidence or service failure, never a
generic `TOTP needed` claim. Ask Tom to forward the receipt only if the
autonomous route has no authorised reader for that mailbox; name that specific
route limitation. Once it appears in a watched inbox, automatic processing
takes over. When the source identity is sufficient, retain the unresolved
expense row in the workbook through `seer_finance`; if that mutation itself
fails, the blocked state is not capture proof.

**Trusted full-body routes available:**

- Microsoft trusted inboxes: `/home/tomdean88/pi-services/trusted-email-reader/read_email.py`;
- Gmail trusted inboxes: `/home/tomdean88/pi-services/trusted-email-reader/read_gmail.py`.

Use the inbox source to choose the correct reader; do not fall back to preview
text when a trusted full-body route exists.

## Canonical workbook contents

The canonical expense record is `/Expenses/Expense ledger.xlsx`. Its existing
visible tables are the place for definite expenses, potential expenses,
pending expense signals, blockers, later rectifications, and
duplicate/false-positive suppression notes. The workbook is the only
operational expense ledger. `reference/OPERATIONAL_ACTIVITY_LOG.md` is a
Tom-facing audit trail for captures, pending blockers, and confirmation state;
it is not a ledger or a write target for the expense record.

If something is expense-shaped enough that dropping it would be unsafe, capture
it in the workbook immediately and rectify/classify later. Do not let a
potential expense live only in side notes, temporary memory, or a
mirror-specific holding document.

This includes items that may later turn out to be:

- true SEER business expenses;
- business-card non-reimbursable spending;
- personal/non-SEER items that should be suppressed after review; or
- duplicate signals already represented elsewhere.

**Capture-provenance rule (MANDATORY):** When answering whether a recent email
expense was already captured, compare the exact source reference in the
current email feed with the workbook and `reference/OPERATIONAL_ACTIVITY_LOG.md`
before replying. State separately: (1) whether it was logged before Tom's
prompt, (2) whether this response created or corrected the row, and (3) any
feed/watcher coverage gap. Never describe a row created during the answer as
evidence that the system captured it automatically.

## Purpose

Keep all business expense information in the canonical workbook. Do not
scatter expense facts across backlog/task files when they belong in the
expense record.

## What goes in the workbook

- actual expenses, both personal out-of-pocket and business card;
- reclaimable costs Tom paid personally;
- business card expenses, tracked but not reimbursable;
- travel and mileage entries;
- invoice and receipt facts;
- expense-specific follow-ups and TODOs;
- notes needed to complete an incomplete expense entry;
- potential, unverified, or pending expense signals strong enough to capture
  now and rectify later; and
- duplicate or false-positive suppression notes when trust requires the reason
  to remain visible.

## What does not go in the workbook

- technical feature gaps or tooling improvements → `BACKLOG.md`;
- general admin tasks not specific to an expense record → `TASKS.md`; and
- temporary chat-only acknowledgements.

## Main rules

1. Check `SYSTEM_MAP.md` if there is any doubt about file placement.
2. Default to updating the current workbook's visible tables through
   `seer_finance`, not creating a new expense file.
3. If another expense file exists, treat it as migration, reconciliation,
   evidence, or recovery input only; preserve source identity and do not make
   it a second operating ledger.
4. If Tom mentions a cost without the amount, capture the expense anyway and
   note what is missing in the workbook.
5. If Tom mentions travel, capture it under Travel & Mileage.
6. If route details are known, calculate and store mileage rather than leaving
   a vague placeholder.
7. If mileage cannot yet be calculated reliably, note the route details and
   missing calculation explicitly.
8. Keep actual expense entries separate from tooling gaps:
   - expense fact → workbook;
   - capability gap, such as a mileage calculator needed → `BACKLOG.md`.
9. If receipts are in inboxes L1 can access, note that in the workbook row and
   preserve the source reference.
10. If Tom forwards receipts into an accessible inbox, re-check live mailbox
    evidence after any trusted-sender change rather than assuming forwarded
    copies remain body-hidden.
11. If Tom provides a vendor billing/invoice-history screen that clearly shows
    invoice rows, dates, amounts, status, or downloadable invoices, treat that
    console view as a valid source for the workbook row. Do not refuse to log
    merely because an email copy or invoice number has not yet been pulled.
12. If receipts are outside accessible inboxes, record the limitation and ask
    Tom to forward them into the accessible flow.
13. **Business card expenses:** if Tom says an expense was paid on the business
    card, flag it as `Business card (not reimbursable)` in the workbook's
    payment/source field. Track it for record-keeping but do not treat it as a
    personal out-of-pocket reimbursement.
14. **Payment-source clarification:** if a new expense, cost, receipt, or
    invoice does not say whether it was paid personally or on the
    company/business card, ask: **"Out of pocket or company card?"** Do not
    assume reimbursement status from the document alone.

### Expense-signal fail-closed rule (MANDATORY)

When any plausible business expense signal appears—from Tom's message, a
forwarded receipt, inbox item, billing-console screenshot, card-charge
mention, travel note, subscription reference, renewal warning, invoice, or
another expense clue—do not leave it floating. This applies across Telegram,
WhatsApp, email, uploaded screenshots/files, photo uploads, transcripts, and
any other surfaced context. In the same working pass, do one of the following:

- for email receipts, use the trusted full-body reader and merge the result
  into the workbook through `seer_finance`;
- for WhatsApp receipts/photos, extract visible details, ask only for missing
  information, and merge immediately;
- for Telegram photo uploads, do the same;
- for verbal mentions, capture the known facts in an unresolved workbook row;
- ask Tom immediately for the missing payment source/detail needed to finish
  the row; or
- explicitly preserve the exact item as pending/blocked with the blocker
  stated.

Silence or deferred good intentions are not acceptable. The capture mechanism
differs by channel, but the fail-closed obligation is the same.

### Single-workbook fail-closed rule (MANDATORY)

If a plausible expense has been seen but the current view lacks its full
amount, reference, or body, that is not permission to skip capture. Preserve a
pending expense signal in the workbook with:

- date seen;
- supplier/vendor;
- source/channel;
- what is known;
- the exact detail still missing; and
- the blocker to full logging.

A Microsoft billing email seen only in an inbox preview is therefore a pending
workbook item, not an omitted item.

### Immediate clarification rule for incomplete chat/WhatsApp expenses

If a WhatsApp/chat expense signal is business-relevant enough to preserve but
too incomplete for a proper row, ask Tom in the same pass for only the missing
fields:

- supplier/vendor or location;
- exact amount;
- date, if ambiguous;
- payment source;
- business purpose; and
- whether receipt/screenshot/evidence exists.

If a short question could resolve a field, a row that still says `Unknown |
TBC` is not a complete pass.

### WhatsApp row-normalization rule

When a WhatsApp expense candidate is strong enough to keep, do not preserve it
as a generic placeholder such as `WhatsApp expense signal | Unknown | TBC` if
the message provides a usable category.

- If it says what it was—bus ticket, parking, networking drinks, coffee, or
  train—use that real category in the workbook immediately.
- If payment source is explicit, carry the exact status into the workbook.
- If it is too weak or non-business after review, classify it as `not_needed`
  in monitored state and do not create a live expense row.
- A self-chat or WhatsApp candidate is not handled merely because a vague
  placeholder exists.

For example, `Bus ticket to Oxford return £6 paid in company credit card.
Today 18th June networking` ends as a travel row; `I've got a £10k deal I am
currently trying to land` does not become an expense row; and `On bus,
20mins` survives only when linked to a stronger expense message in the same
thread/window.

### Explicit non-business override rule

If Tom explicitly says an expense-shaped signal is not to do with the business,
not one of ours, or should be ignored, reclassify it as `not_needed`. Preserve
the source and audit decision in monitored state, and correct any provisional
workbook row through `seer_finance` so it no longer appears as a live business
expense. Do not silently delete the evidence or continue surfacing it unless
Tom reopens it.

### WhatsApp operational-proof rule

If a WhatsApp-origin expense is logged, upgraded, suppressed as a false
positive, or left pending with a blocker, the same pass must leave a
reviewable proof path in both:

- the matching workbook row/state; and
- `memory/monitored-items-state.json` and
  `reference/OPERATIONAL_ACTIVITY_LOG.md`.

Do not treat WhatsApp handling as complete if only chat or monitored state
exists without the canonical workbook outcome.

### Source-landing and realisation dates

For inbox-driven or externally surfaced expenses, the row date corresponds to
when the expense landed in the source system—normally the email `received`
date or provider invoice/created date. Do not replace it with the date L1
noticed or reviewed it.

The row may also preserve when L1 realised, saw, logged, reviewed, or
reconciled it as secondary audit notes:

- `Seen by L1: YYYY-MM-DD HH:MM`
- `Logged by L1: YYYY-MM-DD HH:MM`
- `Reviewed/reconciled by L1: YYYY-MM-DD HH:MM`

The row must answer both "when did this expense land?" and "when did L1
realise it?" without ambiguity.

### Pass-completion and activity logging rules

Before finishing any pass where an expense clue appeared, classify every seen
expense as one of:

- logged in the canonical workbook;
- pending in the workbook with blocker; or
- duplicate already represented.

Every meaningful expense state transition must also be written to
`reference/OPERATIONAL_ACTIVITY_LOG.md` in the same pass:

- fully captured → `Confirmed`;
- preserved pending missing details, access, or feed coverage → `Queued` or
  `Coverage incomplete` with the blocker; and
- deliberately suppressed duplicate → log when the decision is trust-relevant
  or useful for later audit.

Do not leave a seen expense existing only in chat or an activity note.

### Travel and mileage rules

Treat forwarded receipts as only one subtype of expense trigger. Any visible
cost, charge, receipt, travel, or payment hint related to business activity
from any source is presumed to need capture into the workbook.

If Tom mentions travelling to meet someone, going to an event, driving
somewhere, taking a call/meeting away from home, or other business movement,
ask short capture questions while the context is live:

- how did he get there?
- was it out of pocket or company card?
- was there parking, bus, train, or mileage?
- will there be food, coffee, or another cost?
- is there anything else expense-wise to log from the trip?

If a travel signal contains enough information to form a mileage row—such as
destination/purpose plus explicit distance or clearly stated each-way/return
mileage—log it immediately in the workbook, then separately capture attached
costs still missing.

If Tom names a client/site/venue and says a trip happened again, or lists
multiple same-destination visit dates, reconcile the full repeated-route set
in the workbook. Every named trip date gets its own mileage row.

When judging new mileage, search prior workbook rows for the same
destination/client/venue or an equivalent route alias. Reuse an established
distance when clearly the same route; if labels may differ materially, ask Tom
instead of guessing.

### Receipt and payment-evidence retention

If Tom sends a receipt image/file, payment screenshot, bank confirmation, card
screen, invoice PDF, or other business-expense evidence, in the same pass:

- merge/reference the expense in the workbook;
- retain the evidence description, source path, message context, or canonical
  storage reference in the workbook row; and
- use an already-governed binary retention route if one exists.

Do not stop at a local note, create a Markdown expense ledger, or use a
generic SharePoint append/create operation. If binary retention is unavailable,
the workbook row must say `evidence blocked` with the exact blocker.

The completion state for direct evidence is one of:

- `logged + evidence reference retained in workbook`;
- `logged + binary evidence retention queued through an established route`; or
- `logged + evidence blocked` with the exact blocker.

## Tide bank-statement classification tags (MANDATORY)

When reconciling future Tide statements, apply these tags before deciding
whether a movement belongs in the workbook:

- `TIDE_OWNER_SELF_PAY` — any payment to Thomas Dean / Tom, regardless of the
  receiving account. Treat as Tom paying himself; exclude from expenses and
  client revenue unless Tom explicitly reclassifies it.
- `TIDE_PT_INCOME` — inbound £40 payments from Jack, Jess, or Lisel (and future
  equivalent personal-training-hour payments). Treat as personal-training
  income, separate from invoice receipts and never as an expense.
- `TIDE_CLIENT_INVOICE_RECEIPT` — inbound payment with an exact
  invoice/client/reference/amount match. Reconcile against the invoice tracker;
  do not infer a match from amount alone.
- `TIDE_ACCOUNT_TOPUP_OR_REWARD` — Tide rewards, top-ups, and similar
  non-trading account movements; exclude from expenses and revenue unless
  separately identified.
- `TIDE_BUSINESS_EXPENSE_<CATEGORY>` — confirmed business outgoings, using
  `SOFTWARE`, `NETWORKING_MEMBERSHIP`, `TRAVEL`, `MEALS_REFRESHMENTS`,
  `INSURANCE`, `COMPLIANCE`, `BANKING_FEES`, or `OTHER`.
- `TIDE_UNCLASSIFIED_TRANSFER` — any remaining transfer that cannot be safely
  classified from the statement and current rules. Preserve it in the
  reconciliation report and ask Tom/accountant; never silently put it in the
  workbook as an expense.

For every future statement, record the tag in the reconciliation report and,
where it is an expense, in the workbook row notes. This prevents repeated
reclassification conversations across months.

## Settled-classification reuse rule (MANDATORY)

For historic Tide reconciliation, migration, review-state handling, or a
question about an item whose merchant/reference, date/amount pattern,
route, or counterparty matches a classification Tom already supplied, first
check the primary Tide evidence, current reconciliation report, and existing
workbook record. Reuse that outcome and repair the source-linked workbook
record. Re-open a question only when new source evidence materially conflicts
with the recorded outcome; name the conflict precisely.

**Current settled Tide decisions (11 August 2026):**

- any £40 inbound payment is PT income unless strong contrary evidence;
- the £30 Barrett credit on 5 August is a PT session/income;
- each Tide transfer/conversion fee is a separate `BANKING_FEES` line, not a
  monthly aggregate;
- Lycamobile is a business-phone cost;
- APCOA is business parking tied to travel/meetings;
- retained Missing Bean, St Aldates, and other meals/refreshments previously
  tied to travel or meetings are genuine business costs; and
- the April £80 visibility gap is two £40 PT-income entries; technical line
  reconstruction must not reopen their category.

Before asking Tom for historic transaction detail, record the lookup made and
either reuse the settled classification while identifying the remaining
technical/evidence action, or quote the genuinely contradictory new evidence.
Absence of a final workbook row alone fails this test.

## Tom-supplied fact → exact-record update rule (MANDATORY)

When Tom supplies, confirms, or corrects an expense/accounting fact, apply it
to the matching source-linked workbook row in the same pass—not only to chat,
memory, a future task, or a general policy rule. Add it as structured field
data where the table supports it; otherwise add a dated audit note with source
and message provenance. Preserve conflicting historic values and audit history;
do not overwrite or delete them.

Where a supplier invoice/receipt exists, retain an evidence reference with the
canonical storage location and original filename, for example
`SharePoint:/Expenses/SEER/2026-08-06 - Invoice - Microsoft Azure AI - G175174660.pdf`.
A filename alone is insufficient. Add an immutable SharePoint item/document ID
when the evidence-link schema supports it. Never replace the payment/bank
source reference merely to add invoice evidence.

If the workbook update is technically unavailable, create a durable `blocked`
transition against that exact record with the machine-readable blocker and
surface it as a finance-system health issue. Do not ask Tom for the same fact
again. On recovery, apply retained facts to the exact workbook records before
new reconciliation questions.

## Closure-state ledger

- Shared monitored-item proof layer: `memory/monitored-items-state.json`.
- Expense truth: the visible tables in `/Expenses/Expense ledger.xlsx`.

The monitored-item layer cannot close an item merely because it says `closed`;
compare it with the canonical workbook outcome and the operational activity log
in the same pass.

## Books-ready / profit-status output rule (MANDATORY)

**Trigger:** Tom asks an equivalent of `what remains?`, `what decisions do we
need?`, `what do we have to do to get the books ready?`, `is the bookkeeping
correct?`, or `what profit have I made?`.

Do not answer with a profit headline or expense total alone. Before presenting
any figure, build a **books-ready closure view** from the canonical workbook
and the most recent available primary Tide/card evidence:

1. Reconcile the workbook's confirmed, unresolved, blocked, and duplicate
   outcomes against that primary evidence.
2. Separate every item into `verified and posted`, `needs source evidence`,
   `needs Tom decision`, `needs accountant/tax-policy decision`, or
   `coverage unavailable`.
3. For every non-closed item, state the exact item/amount where known, the
   decision or evidence needed, the owner, and the consequence for reported
   profit/readiness.
4. State whether the result is a management figure,
   reconciliation-complete figure, or statutory-ready figure. Do not call the
   books ready while primary bank/card coverage is missing or a material
   candidate/decision is unresolved.
5. Finish with the shortest concrete closeout checklist in dependency order.

If the current Tide/card statement period does not cover the requested profit
period through its end date, label the result `coverage incomplete` and name
the exact missing statement/export range. A workbook row, inbox email, or
retained invoice is not a substitute for primary settlement evidence.

## Workflow

1. Read the current `/Expenses/Expense ledger.xlsx` cache, visible tables,
   source references, and native `eTag`.
2. Check whether the expense already exists by exact source identity,
   invoice/reference, and relevant date/amount—not supplier name alone.
3. If any expense signal is in scope, run triage immediately:
   - enough detail to log now?
   - missing payment source?
   - missing gated/full-body access?
   - duplicate already represented?
4. Merge the new or corrected row into the current workbook while preserving
   tables, sheets, existing rows, source references, receipt evidence, and
   unresolved fields.
 5. Submit exactly one complete workbook mutation through
    `get_boundary().write_workbook_verified(...)`; its worker consumes the
    resulting `operation: "update_workbook"` request with all hashes and the
    native `eTag`.
6. If information is incomplete, preserve a precise pending/blocked state in
   the workbook and monitored proof layer.
7. For forwarded receipts, a visible preview is not enough when the exact
   amount/reference is needed. Use the approved autonomous full-body route. If
   the reader fails, preserve known date/reference, mark amount unverified,
   record the exact service error, and leave it for autonomous retry.
8. If the expense reveals a technical/system gap, record that separately in
   `BACKLOG.md`.
9. If duplicate or legacy records exist, reconcile them into the workbook only
   under a migration/reconciliation action with source identity preserved; do
   not establish a second operating ledger.
10. When an expense-shaped email is seen in any inbox surface, reconcile that
    exact email against the workbook and evidence-retention state before
    finishing the pass. A watcher statement such as "preserved", "logged", or
    "handled" is only an intake claim, not canonical proof.
11. For each seen item, explicitly classify:
    `logged` / `duplicate already represented` / `pending with blocker`; and
    separately classify evidence as `reference retained` / `queued through an
    established route` / `blocked`.
12. For a monitored inbound signal, leave a durable proof path through the
    workbook plus monitored state and/or operational activity log. If the pass
    cannot safely prove completion, classify it as `blocked` or `coverage
    incomplete`.
13. Before finishing, state whether every newly seen forwarded receipt was
    handled as logged, blocked-and-raised, or duplicate-already-represented.

## Quality test

Before finishing, check:

- Is `/Expenses/Expense ledger.xlsx` still the single operational source of
  truth?
- Did every canonical mutation use the public `seer_finance` XLSX boundary,
  the current native `eTag`, all required hashes, and a complete merged
  workbook?
- Did the workbook retain its existing tables, sheets, rows, source
  references, receipt evidence, and unresolved fields?
- Did I avoid putting expense facts into the wrong file or creating a Markdown
  substitute?
- If the amount is unknown, did I preserve the known facts and exact blocker?
- If travel was mentioned, did I capture route context and mileage status?
- Is the remote binary/semantic/readback proof present before claiming capture?

## Mandatory end-of-use review

After every real use of this skill, do a short explicit pass with Tom on
whether anything in the skill itself should be updated. Treat that review as
part of completion, even if the outcome is "no skill changes needed".