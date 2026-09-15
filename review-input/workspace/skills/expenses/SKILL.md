---
name: expenses
description: Record, maintain, and consolidate SEER business expenses into the single canonical expense file. Use when Tom mentions a cost, reimbursement, mileage/travel, invoice, subscription, hardware purchase, domain renewal, or receipt follow-up.
last_edited: 2026-06-11 17:24
---

# Expenses

## Immediate capture contract (MANDATORY — takes precedence over all older wording below)

When Tom gives an expense in chat, email, WhatsApp or a receipt/image, capture it in the **SQLite `expenses` ledger immediately** through the direct expense-capture service. Do not write it to `seer-expenses.md`, do not make a legacy file the proof of capture, and do not put an ordinary text-only expense behind an asynchronous receipt/replay queue.

- Missing amount, exact date, supplier, payment source, category or receipt is **not** a reason to defer a plausible expense. Create a source-linked SQLite `needs_review` record with every known fact and an exact missing-detail/evidence state.
- For a receipt/image/PDF, retain the original binary first in the governed receipt-evidence path, hash it, queue/upload it to SharePoint, then append the SharePoint path/eTag/hash as immutable SQLite receipt evidence. Extract and capture every fact visible in the item; unresolved fields remain `needs_review`.
- For text-only expenses, direct SQLite capture and a source-linked read-back are the completion proof. A receipt is desirable evidence, not a prerequisite for capture.
- A replay/repair worker is only a recovery path after a direct capture/evidence attempt fails. It is never the normal path that Tom waits on.
- Before reporting capture, return the SQLite expense ID and state. Before reporting receipt retention, return the receipt hash plus SharePoint path/eTag and linked SQLite evidence ID.

## Position in the broader managed-item model
Expenses are one **owning workflow** beneath the broader inbound/outbound managed-item system.
The first question for any email/message/event is not "is this an expense?" but:
- **is this a thing that needs management?**

If yes, one possible route is `EXPENSE`.
This skill governs what happens after an item has been assessed as expense-relevant or expense-shaped.

## Finance-system routing contract (MANDATORY — takes precedence over legacy Markdown wording below)

Use `reference/SEER-EXPENSE-OPERATIONAL-LEDGER.md` before changing the finance service, migration, writer, review tray or reconciliation.

- **Expense SQLite (`expenses`):** retain every plausible *expense* candidate immediately, even if incomplete; it must never contain an explicitly income-direction record.
- **Finance ledger (`finance_transactions`):** contains confirmed income and only high-confidence, evidence-backed expenses. It is not a holding queue.
- **Holding tray:** exposes SQLite `needs_review`/`blocked` expense records. Incomplete, duplicate, conflicting or Tide-unmatched expense candidates remain here and cannot post.
- **Income:** stays out of the expense database and tray. Preserve primary source evidence and route it only through finance-ledger/Tide reconciliation.
- **Duplicates:** never auto-delete, overwrite or silently merge. An explicit reviewer outcome may hide a duplicate from the working tray, but source evidence and immutable audit history remain.
- **Evidence priority:** original Tide statements/exports are primary accounting evidence; SQLite is operational truth only to the extent supported by reconciliation; legacy Markdown/JSON are retained secondary evidence during migration.

The historical `seer-expenses.md` capture rules below remain a preservation fallback until the direct SQLite intake route and user-accessible review tray are fully proven. Do not claim cutover, retirement or single-writer status without the proof requirements in the governing design.

## Autonomous no-TOTP invariant (MANDATORY)

The expense watcher, capture queue, rectification/enrichment worker, database review tray and finance-validation/reconciliation path are autonomous Pi services. **They must never require Tom to provide TOTP for routine capture, preservation, classification, review-queue display, enrichment, validation, reconciliation, or health checks.**

- The runtime must use its own least-privilege local service access and durable source-linked state; it must not depend on an L1 chat turn or an interactive approval window.
- If a dependent reader, database, file path or service fails, it must preserve the candidate as `blocked` with the exact machine-readable failure and surface it in health/review state. It must not ask Tom for TOTP as a fallback.
- TOTP is permitted only for an explicitly user-authorised exceptional privileged change outside the normal expense operating path (for example host-level service installation or credential rotation). It is never a prerequisite for processing an expense candidate already in a monitored surface.
- Every integration or live-acceptance test for this system must prove the source → capture/review → validation path with no interactive approval.

### Chat-side gate diagnosis (MANDATORY)

**Trigger:** an assistant sees an expense signal or reports that a reader/writer is gated, blocked, or needs approval.

**Required mechanism:** first read this invariant, `SYSTEM_MAP.md`, and the live owning service/state; then resolve the **declared non-gated route** all the way to its concrete invocation contract (service/API/queue file, required payload fields, worker/consumer, and destination proof). Attempt that route before considering any shell/exec path. Only then distinguish a *chat-shell execution gate* from the autonomous expense service's own least-privilege route. A chat-shell gate, or inability to use arbitrary `exec`, is never evidence that routine expense processing requires TOTP.

**Route-discovery receipt:** before saying a capture/write route is unavailable, name: (1) the exact governing skill read, (2) the non-gated route identifier, (3) its concrete input contract, (4) its runtime consumer, and (5) the SQLite/SharePoint read-back that would prove success. If any element is unknown, discovery is incomplete — inspect the declared route’s implementation/contract rather than substituting a familiar command or asking Tom for TOTP.

**Fail-closed outcome:** if the autonomous route truly fails, preserve the exact candidate as `blocked` with its machine-readable service error and surface the health/review state. Do not ask Tom to unlock ordinary reading or writing. Ask for approval only when the requested work is a separately privileged system change, and name that change.

## Preservation-first data invariant (MANDATORY)

For expense capture, rectification, ledger migration and reconciliation, **data loss is worse than duplication**. Preserve every source/evidence row and conflicting value; only an exact replay may be represented idempotently. A non-identical collision or ambiguous duplicate must remain as a separately auditable `needs_review`/`blocked` record with both references—never be deleted, overwritten or silently merged. Legacy files become read-only archive evidence only after row-count/checksum reconciliation proves that every item has either a database destination or an explicit retained-review state.

## SQLite backup invariant (MANDATORY)

Every production SQLite expense/finance database is a canonical financial record and must be included in the established code-and-files backup cadence, retention and restore test. Use a SQLite-consistent snapshot; write a dated backup manifest with database checksum, schema version and source watermark; and surface a missed/failed backup as an expense-system health blocker. Do not place an SQLite file in an untracked runtime location or treat a repository commit as a substitute for a database backup.

## Mirror timestamp and Telegram-evidence invariant (MANDATORY)

A mirror `source_timestamp` is untrusted evidence, not safe operational control data. The expense watcher must retain the raw value but validate it before using it for queue ordering, display or state: malformed or materially future timestamps use the watcher observation time and carry an explicit invalid status. A central `EXPENSE` flag on a Telegram conversation is insufficient by itself; it needs concrete transactional evidence (for example a monetary value, receipt, invoice, order, charge/payment, purchase, renewal, subscription, refund or reimbursement) before an unresolved expense queue record is created. A downgraded non-financial event remains traceable in monitored/source evidence as `not_needed`; it is not silently deleted.

## Automatic Expense Email Processing (MANDATORY)

**Cross-inbox sweep rule (MANDATORY):**
When checking recent expenses or when any one expense email is found, do not stop at the current inbox. Sweep **all relevant expense inbox surfaces** in the same pass:
- `GMAIL_INBOX.md`
- `ASSISTANT_INBOX.md`
- `MICROSOFT_INBOX.md`
- and, when relevant, the matching external/secondary feed if the expense may not yet be present in the trusted view

Classify every recent expense-shaped email/signal into the managed-item seriousness model with the exact expense outcome preserved underneath it:
- `processed` (for example logged)
- `closed` (for example duplicate already logged and fully satisfied)
- `blocked` (for example pending with blocker)
- `not_needed`

Do not finish the expense pass until all relevant visible surfaces have been checked.

**Feed-completeness fail-closed rule (MANDATORY):**
If I am asked whether recent expense emails were processed, I must check the `Last updated:` timestamps on the inbox feed files before claiming coverage. If any feed is stale, if Tom says there are newer emails than the feed shows, or if Tom provides screenshot/browser evidence of an expense email not present in the markdown feeds, I must treat the sweep as **incomplete**, not as proof that no other expense exists.

Concrete mechanism:
- read the inbox feed timestamps
- compare them against the claimed/visible missed email timing
- if the feed predates the evidence or does not show the shown message, classify the item as `blocked` with blocker detail `feed gap / not yet visible in markdown`
- do **not** say the system processed "recent ones properly" until that gap is resolved

**Recent-mirror supplier sweep rule (MANDATORY):**
When Tom says there should be a newer expense email in "the email mirror" or challenges whether I missed a newer supplier email, I must run a supplier-targeted sweep across **all mirrored inbox surfaces**, not just the first mailbox where I previously looked.

Concrete mechanism:
- identify the supplier or receipt family from Tom's challenge (for example `GitHub`, `Replit`, `Microsoft`)
- read the newest relevant external/trusted mirror files for that supplier: `GMAIL_EXTERNAL.md`, `MICROSOFT_EXTERNAL.md`, `ASSISTANT_EXTERNAL.md`, plus trusted inbox mirrors if relevant
- search for the supplier/receipt subject family and compare timestamps so I can name the newest visible matching email
- reconcile that exact newest visible item against `seer-expenses.md`
- if the newest visible item is absent from the expense log, answer `seen but not fully processed` rather than implying capture from an older matching row

Fail-closed test:
- if an older GitHub row exists in `seer-expenses.md` but `GMAIL_EXTERNAL.md` shows a newer GitHub receipt, I must surface the newer one explicitly and not answer from the older row
**Email-landed trigger rule (MANDATORY):**
If any inbox-check, heartbeat, sent-items review, or manual email pass encounters a plausible expense-related email, that sighting itself is the trigger to act. Do not wait for Tom to later ask about expenses.

Required action chain:
1. inspect the email through the approved autonomous reader route
2. use the service's fixed least-privilege reader and capture/writer path; never substitute a chat-shell gate for that route
3. if the reader, attachment download, extraction or writer fails, classify the item as **blocked** with the exact service failure and preserve it for autonomous retry
4. classify the item as processed / blocked / closed / not_needed with the exact supporting expense outcome before finishing the email pass

**Trusted-inbox closure-proof rule (MANDATORY):**
For expense-shaped emails in `ASSISTANT_INBOX.md`, `MICROSOFT_INBOX.md`, or `GMAIL_INBOX.md`, inbox visibility is only the **arrival signal**, not proof of processing.

Before claiming a trusted-inbox expense email was handled, I must be able to prove one of these outcomes in the same working pass:
- a matching row was added/updated in `seer-expenses.md`, or
- the item was classified as duplicate already logged, or
- the item was preserved as pending/blocked with the exact blocker named in `seer-expenses.md`, or
- the item was explicitly judged `not needed` with a reason only if it is truly non-expense

Concrete mechanism:
- read the newest visible trusted-inbox expense emails
- compare them against `seer-expenses.md`
- if the email is visible in inbox but no matching expense outcome exists yet, the status is **not processed**
- in that case, I must not imply the system handled it; I must classify it immediately as processed / closed / blocked / not_needed, with the exact supporting expense outcome named

Audit fail-closed test:
- if Tom asks "did you get/process the newer expense email?" and the inbox contains it but `seer-expenses.md` or the explicit pending/blocked record does not, I must answer: **seen but not yet processed**
- even after logging, do not imply the item is `closed` unless the owning expense workflow has actually finished the required downstream steps for that item

**Newest-invoice same-pass rule (MANDATORY):**
When a trusted inbox shows a newly landed supplier invoice/receipt email for a recurring vendor already present in `seer-expenses.md` (for example Microsoft, Anthropic, OpenAI, Replit), I must not treat the existence of older rows for that supplier as evidence the new one was handled.

Concrete mechanism:
- extract the newest visible invoice/receipt identifiers from the trusted inbox entry itself first: supplier + invoice number/reference + landed date
- search `seer-expenses.md` for that exact invoice/reference (not just the supplier name)
- if the exact invoice/reference is absent, log the new row immediately or preserve it as pending/blocked with the exact blocker
- then add/update `ACTIONED.md` only after the new specific invoice/reference has a matching handled outcome

Fail-closed test:
- a new inbox item like `Your Microsoft invoice G168579299 is ready` is **not handled** merely because older Microsoft invoices already exist in `seer-expenses.md`
- the exact invoice number must exist in the expense log or in a pending/blocked record before I can claim capture

**No-gap overnight invoice rule (MANDATORY):**
A newly landed trusted-inbox expense email must be captured on the first pass that reads that feed, even if the dedicated expense watcher has not yet run, is disabled, or another broad inbox cron has not fired yet.

Concrete mechanism:
- trigger = any process/skill/manual check that reads `MICROSOFT_INBOX.md`, `GMAIL_INBOX.md`, or `ASSISTANT_INBOX.md`
- on that same pass, scan the newest trusted-inbox items for expense-source patterns
- for each matching item, perform the exact-invoice check above against `seer-expenses.md`
- if missing, create the expense row immediately; do not defer it to a later generic inbox watch just because the feed was read by a different workflow first

This prevents overnight invoice emails from sitting visible in a trusted inbox until a later unrelated cron happens to pick them up.

**When an expense-source email appears in ASSISTANT_INBOX.md or any trusted inbox:**

**IMMEDIATELY process it automatically (no TOTP required):**

1. **Extract message ID** from the inbox markdown
2. **Call the correct trusted reader:**
   - For `ASSISTANT_INBOX.md` →
   ```bash
   python3 /home/tomdean88/pi-services/trusted-email-reader/read_email.py \
     <message_id> --account assistant --download-attachments
   ```
   - For `MICROSOFT_INBOX.md` →
   ```bash
   python3 /home/tomdean88/pi-services/trusted-email-reader/read_email.py \
     <message_id> --account microsoft --download-attachments
   ```
   - For `GMAIL_INBOX.md` →
   ```bash
   python3 /home/tomdean88/pi-services/trusted-email-reader/read_gmail.py \
     <message_id> --download-attachments
   ```
3. **Parse the JSON response** to extract:
   - Subject
   - Date (from "received" field)
   - Amount (parse from HTML body)
   - Receipt/invoice numbers
   - Attachments (already downloaded to expense-attachments/)
4. **Log to seer-expenses.md** immediately with complete details
5. **Queue SharePoint artifact** if PDFs were downloaded

**Expense-source patterns to match:**
- Subject contains: "receipt from Anthropic" | "receipt from Replit" | "OpenAI API Invoice" | "Your OpenAI API account has been funded" | "Your Microsoft invoice"
- Sender: invoice+statements@mail.anthropic.com | noreply@billing.replit.com | noreply@tm.openai.com | microsoft-noreply@microsoft.com

**OpenAI top-up rule (MANDATORY):**
Treat OpenAI "account funded" / credit-top-up emails as expense signals in the same way as OpenAI invoice emails. If the exact invoice document is not yet visible, still log a pending expense signal with the date, visible amount, source channel, and blocker rather than leaving it uncaptured.

**Amount extraction patterns:**
- Anthropic HTML: look for `<span>` with `font-size:36px` containing `$XX.XX`
- OpenAI HTML: look for `<b>$X.XX</b> USD` in body text
- Replit HTML: similar to Anthropic (Stripe-based)
- Extract both subtotal and total (prefer total)

**Why:** With trusted-email-reader, we can process expense emails immediately without TOTP or manual forwarding. Complete automation from arrival to logged expense.

**Mirror-layer guarantee rule (MANDATORY):**
The guarantee that an expense signal will be handled must live at the **mirror/watch layer**, not only inside the full-body reader route.
If an item appears in a mirrored inbox, sent-items view, WhatsApp recent feed, or similar monitored surface and looks expense-shaped, that appearance itself must create one of these managed-item outcomes in the same pass:
- `processed`
- `closed`
- `blocked`
- `not_needed`

The exact expense outcome still needs to be named beneath that state (for example logged, duplicate already logged, pending with exact blocker).
Do not let a suspicious item disappear merely because the extractor, trusted reader, or richer route failed.

**Automatic trigger path:**
- Pi-native watcher code: `/home/tomdean88/openclaw/pi-services/expense-intake-watcher/watcher.py`
- Runtime state/log source of truth: `~/.openclaw/runtime/expense-intake-watcher/state.json` and `~/.openclaw/runtime/expense-intake-watcher/watcher.log`
- Watches new items across `GMAIL_INBOX.md`, `ASSISTANT_INBOX.md`, and `MICROSOFT_INBOX.md`
- Reads new expense-shaped mail through the trusted reader routes
- Logs new rows into `seer-expenses.md`
- Do not diagnose freshness from the repo copy under `~/pi-services/expense-intake-watcher/`; that location is not the live state source.

**For external inbox emails (body hidden):**
If an expense email appears in MICROSOFT_EXTERNAL.md or GMAIL_EXTERNAL.md:
- Preserve it immediately as a source-linked `blocked` candidate and route it into the autonomous enrichment/replay path; do **not** demand a chat TOTP as a substitute for that worker.
- The blocker must name the actual missing evidence or service failure, never a generic `TOTP needed` claim.
- Ask Tom to forward the receipt only if the autonomous route has no authorised reader for that mailbox; name that specific route limitation.
- Once it appears in a watched inbox, automatic processing takes over.

**Trusted full-body routes available:**
- Microsoft trusted inboxes: `/home/tomdean88/pi-services/trusted-email-reader/read_email.py`
- Gmail trusted inboxes: `/home/tomdean88/pi-services/trusted-email-reader/read_gmail.py`
- Use the inbox source to choose the correct reader; do not fall back to preview text if a trusted full-body route exists

Use this skill for business expense logging and expense-file maintenance.

## Canonical file
- `seer-expenses.md` = single source of truth for **all** SEER expense tracking, including definite expenses, potential expenses, pending expense signals, blockers, later rectifications, and duplicate/false-positive suppression notes
- `reference/OPERATIONAL_ACTIVITY_LOG.md` = Tom-facing audit trail for expense captures, pending blockers, and confirmation state

## Canonical operating rule
There is **one governing skill** for expenses: `skills/expenses/SKILL.md`.
There is **one canonical expense log**: `seer-expenses.md`.

If something is expense-shaped enough that dropping it would be unsafe, capture it in `seer-expenses.md` immediately and rectify/classify later. Do not let potential expenses live only in side notes, temporary memory files, or mirror-specific holding documents.

This includes items that may later turn out to be:
- true SEER business expenses
- business-card non-reimbursable spends
- personal/non-SEER items that should be suppressed after review
- duplicate signals already represented elsewhere

**Capture-provenance rule (MANDATORY):** When answering whether a recent email expense was already captured, compare the exact source reference in the current email feed with both `seer-expenses.md` and `reference/OPERATIONAL_ACTIVITY_LOG.md` before replying. State separately: (1) whether it was logged before Tom's prompt, (2) whether this response created or corrected the row, and (3) any feed/watcher coverage gap. Never describe a row created during the answer as evidence that the system captured it automatically.

Capture first in the one log; decide later. The risk posture for SEER finance is fail-closed on misses.

## Purpose
Keep all business expense information in one place.
Do not scatter expense facts across backlog/task files when they belong in the expense record.

## What goes in `seer-expenses.md`
- actual expenses (both personal out-of-pocket and business card)
- reclaimable costs Tom paid personally
- business card expenses (tracked but not reimbursable)
- travel / mileage entries
- invoice / receipt facts
- expense-specific follow-ups and TODOs
- notes needed to complete an incomplete expense entry
- **potential / unverified / pending expense signals** that are strong enough to capture now and rectify later
- duplicate / false-positive suppression notes when trust requires the reason to remain visible

## What does NOT go in `seer-expenses.md`
- technical feature gaps or tooling improvements → `BACKLOG.md`
- general admin tasks not specific to an expense record → `TASKS.md`
- temporary chat-only acknowledgements

## Main rules
1. Check `SYSTEM_MAP.md` if there is any doubt about file placement.
2. Default to updating `seer-expenses.md`, not creating a new expense file.
3. If another expense file exists, merge useful content into `seer-expenses.md` and mark the duplicate for deletion.
4. If Tom mentions a cost without the amount, log the expense anyway and note what is missing.
5. If Tom mentions travel, log it under Travel & Mileage.
6. If route details are known, calculate/store mileage rather than leaving a vague placeholder.
7. If mileage cannot yet be calculated reliably, note the route details and the missing calculation explicitly.
8. Keep actual expense entries separate from tooling gaps:
   - expense fact → `seer-expenses.md`
   - capability gap (e.g. mileage calculator needed) → `BACKLOG.md`
9. If receipts are in inboxes L1 can access, note that in the expense record.
10. If Tom forwards receipts into an accessible inbox (for example from another personal/business account into `assistant@`), re-check the live mailbox evidence after any trusted-sender change rather than assuming the forwarded copies are still body-hidden.
11. **Console-truth rule:** if Tom provides a vendor billing/invoice-history screen that clearly shows invoice rows, dates, amounts, status, or downloadable invoices (for example Claude Console / Anthropic billing history), treat that console view as a valid source of truth for logging those entries. Do not refuse to log just because the email copy or invoice number has not yet been pulled.
12. If receipts are outside accessible inboxes, note that Tom must forward them into the accessible flow.
11. **Business card expenses:** If Tom says an expense was paid on the business card, flag it as "Business card (not reimbursable)" in the Supplier column — these are tracked for record-keeping but are not personal out-of-pocket reimbursements.
12. **Payment-source clarification rule:** If Tom gives you a new expense/cost/receipt/invoice and does not say whether it was paid personally or on the company/business card, ask a short clarification before finalizing the entry: **"Out of pocket or company card?"** Do not assume reimburseable status from the document alone.
13. **Expense-signal fail-closed rule (MANDATORY):** When you encounter any plausible business expense signal — from Tom's message, a forwarded receipt, an inbox item, a billing console screenshot, a card charge mention, travel note, subscription reference, renewal warning, invoice, or any other expense clue you hear/see/infer — you must not leave it floating. This applies across **all visible channels and sources**: Telegram, WhatsApp, email (tomdean1988@gmail.com, assistant@stackstoneconsulting.co.uk, Tom@stackstoneconsulting.co.uk), uploaded screenshots/files, photo uploads, transcripts, and any other surfaced context. In the same working pass, do one of these:
   - **For email expense receipts** in ASSISTANT_INBOX.md, MICROSOFT_INBOX.md, or GMAIL_INBOX.md: use trusted-email-reader to extract full details automatically (no TOTP needed)
   - **For WhatsApp receipts/photos:** extract visible details, ask for missing info (amount/date/vendor), log immediately
   - **For Telegram photo uploads:** same as WhatsApp — extract what's visible, ask for gaps, log
   - **For verbal mentions:** capture immediately to `seer-expenses.md` with whatever details Tom provides, mark pending fields explicitly
   - Log it to `seer-expenses.md` if the key facts are available
   - Ask Tom immediately for the missing payment-source/detail needed to finish logging
   - Or explicitly mark the exact expense item as pending with the blocker stated
   
   Silence or deferred good intentions are not acceptable. The capture mechanism differs by channel, but the fail-closed obligation is the same.
14. **Single-log fail-closed rule (MANDATORY):** If you have **seen** a plausible expense but cannot yet extract the full amount/reference/body from the current view, that is **not** permission to skip capture. You must still preserve it in `seer-expenses.md` as a pending expense signal with:
   - date seen,
   - supplier/vendor,
   - source/channel seen in,
   - what is known,
   - what exact detail is still missing,
   - and the blocker to full logging.
   Example: a Microsoft billing email seen in inbox preview but not yet opened must still be captured as a pending Microsoft expense item rather than omitted.

15. **Immediate clarification rule for incomplete chat/WhatsApp expenses (MANDATORY):** If a WhatsApp/chat expense signal is business-relevant enough to preserve but still too incomplete for a proper row, do **not** stop at a vague pending signal. In the same pass, ask Tom the shortest possible field-completion questions for the missing canonical row fields.

   Minimum fields to force toward completion:
   - supplier/vendor or location
   - exact amount (if not already explicit)
   - date (if ambiguous)
   - payment source (if not already explicit)
   - business purpose / what it was for (if not obvious)
   - whether receipt/screenshot/evidence exists

   The question set must be selective, not boilerplate: only ask for the fields that are actually missing.

   Fail-closed test: if the resulting row would still say `Unknown | TBC` where a short question to Tom could have resolved it, the pass is incomplete.
16. **WhatsApp row-normalization rule (MANDATORY):** When a WhatsApp expense candidate is strong enough to keep, do **not** preserve it in `seer-expenses.md` as a generic placeholder row like `WhatsApp expense signal | Unknown | TBC` if the message already provides a usable category.

   Required behavior:
   - if the message clearly says what it was (`bus ticket`, `parking`, `networking drinks`, `coffee`, `train`, etc.), log/update the row under that real expense category immediately
   - if payment source is already explicit (`company card`, `business card`, `out of pocket`), carry that exact status into the canonical row
   - if the message is too weak or non-business after review, classify it as `not_needed` in monitored state rather than polluting `seer-expenses.md`
   - never let a self-chat or WhatsApp candidate count as "handled" merely because a vague placeholder row exists

   Mechanism test:
   - a message like `Bus ticket to Oxford return £6 paid in company credit card. Today 18th June networking` must end as a real travel row, not `Unknown | TBC`
   - a message like `I've got a £10k deal I am currently trying to land` must **not** become an expense row at all
   - a weak contextual line like `On bus, 20mins` must only survive if linked to a stronger expense message in the same thread/window; otherwise it becomes `not_needed`
17. **Explicit non-business override rule (MANDATORY):** If Tom explicitly says an expense-shaped signal is **not to do with the business / not one of ours / ignore it**, that instruction overrides prior tentative capture. Reclassify the item as `not_needed`, remove or suppress any pending SEER expense row for it, and do not continue surfacing it in expense summaries.

   Mechanism test:
   - trigger: Tom directly labels the seen item as unrelated/non-business/ignore
   - action: find the matching pending row or signal, remove it from `seer-expenses.md` (or mark/suppress it so it no longer appears as a live business expense), and treat future mentions as excluded unless Tom reopens it
   - proof: the item no longer appears in the active SEER ledger as a pending business expense
18. **WhatsApp operational-proof rule (MANDATORY):** If a WhatsApp-origin expense is logged, upgraded, suppressed as false-positive, or left pending with blocker, the same pass must also leave a reviewable proof path in both:
   - `memory/monitored-items-state.json`
   - `reference/OPERATIONAL_ACTIVITY_LOG.md`

   Do not treat WhatsApp expense handling as complete if the row exists in `seer-expenses.md` but the monitored-state/log layers cannot show whether it was a real expense, a false positive, or still blocked.
18. **Source-landing date rule (MANDATORY):** For inbox-driven or externally surfaced expenses, the **row date must correspond to when the expense landed in the source system** — normally the email `received` timestamp date or the provider's invoice/created date shown in billing history. This primary date is what Tom should be able to use to find the matching bank transaction, receipt, or inbox item later. Do **not** replace that primary row date with the date L1 noticed/reviewed it.
16. **Realisation/audit-date rule (MANDATORY):** Whenever an expense is logged, reviewed, reconciled, or challenged, the record may also preserve **when L1 actually realised/saw/logged it**, but only as secondary audit notes. If the detection date differs from the source landing date, add note text such as:
   - `Seen by L1: YYYY-MM-DD HH:MM`
   - `Logged by L1: YYYY-MM-DD HH:MM`
   - `Reviewed/reconciled by L1: YYYY-MM-DD HH:MM`
   Fail-closed test: if Tom asks either "when did this expense land?" or "when did L1 realise it?" the row should answer both without ambiguity.
17. **Pass-completion test (MANDATORY):** Before finishing any working pass where an expense clue appeared, explicitly classify every seen expense as one of:
   - **logged**
   - **pending in `seer-expenses.md` with blocker**
   - **duplicate already logged**
   If you cannot classify it into one of those three buckets, the expense pass is incomplete and you must not move on.
18. **Operational activity logging rule (MANDATORY):** Every meaningful expense state transition must also be written to `reference/OPERATIONAL_ACTIVITY_LOG.md` in the same pass.

Required mechanism:
- if the expense is fully captured → log `Confirmed`
- if it is preserved pending missing details/gate/feed gap → log `Queued` or `Coverage incomplete` with the blocker named
- if it is deliberately suppressed as duplicate → log only when that duplicate decision is trust-relevant or useful for later audit
- do not leave a seen expense existing only in `seer-expenses.md` or only in chat when Tom would reasonably expect a review trail
16. **Expense-signal detection rule (MANDATORY):** Treat forwarded receipts as only one subtype of expense trigger. Your default assumption must be that any visible cost/charge/receipt/travel/payment hint related to business activity from any channel/source Tom uses is something he expects captured into the expense system and, where the route exists, filed to the SharePoint expense record as well.
17. **Travel follow-up rule (MANDATORY):** If Tom mentions travelling to meet someone, going to an event, driving somewhere, taking a call/meeting away from home, or any other business movement that plausibly creates costs, do not just note the meeting. Ask short capture questions while the context is live, for example:
   - how did you get there?
   - was it out of pocket or company card?
   - any parking / bus / train / mileage?
   - will you be eating / buying coffee / anything else worth capturing?
   - anything else expense-wise I should log from this trip?
   The goal is to surface likely attached expenses before they are forgotten.

18. **Standalone mileage-immediacy rule (MANDATORY):** If a travel signal already contains enough information to form a mileage row — for example destination/purpose plus explicit distance or a clearly stated each-way / return mileage — log the mileage entry to `seer-expenses.md` immediately in the same pass. Do not leave mileage implicit just because related attached costs (parking, food, drinks, tickets) are still pending.

   Example trigger:
   - `I am driving to Pentahotel for a talk: 24.6 miles each way`

   Required behavior:
   - create the mileage row immediately
   - then separately capture/clarify any attached travel expenses still missing

   Fail-closed test: if mileage could already have been logged from the message but I only preserved it as context for another expense, the pass is incomplete.
19. **Repeated-route mileage reconciliation rule (MANDATORY):** If Tom names a client/site/venue and indicates that a trip happened again, or lists multiple same-destination visit dates, do not check only the latest visible row. Reconcile the full repeated-route set for that destination in `seer-expenses.md` and ensure every named trip date has its own mileage row.

   Mechanism:
   - trigger: Tom says a journey happened again, says there have been more visits, or lists multiple dates for the same destination
   - read `seer-expenses.md`
   - search for the destination/client pattern (for example `Croyde Medical`)
   - compare existing row dates against the dates Tom named
   - add any missing dated mileage rows before replying

   Mechanism test:
   - if Tom says `today, yesterday, 10th June, April 28, March 17` for the same client trip, the pass must end with five dated mileage rows, not just an updated latest row
   - this would have caught the original failure because a destination-wide date reconciliation would have shown only two Croyde rows present
   - sustainable because it is a cheap destination-pattern scan within one file
20. **Known-route mileage reuse rule (MANDATORY):** When judging a new mileage expense, first look for an existing row in `seer-expenses.md` for the same destination/client/venue or an obviously equivalent route alias before treating the distance as unknown.

   Required behavior:
   - search for prior rows using company/site/venue names and close variants (for example client name, venue name, town, or known alias)
   - if a prior row clearly establishes the same route distance, reuse that distance for the new row instead of leaving it `TBC`
   - if the new route appears to be the same place under a different label (for example venue vs parking name nearby), normalize them to one shared distance once Tom confirms equivalence
   - if there is any real ambiguity, ask Tom rather than guessing

   Mechanism test:
   - if `Pentahotel Reading` already exists and a new row says `Reading Q-Park`, check whether that is effectively the same trip before inventing a second unknown distance
   - if `Leonardo Royal Hotel Oxford` already has a confirmed return mileage, reuse it for later `OBCN breakfast` rows
   - if two possible destinations in the same town could differ materially, ask Tom which one it was
21. **Receipt/payment-evidence retention rule (MANDATORY):** If Tom sends a receipt image/file, payment screenshot, bank confirmation, card screen, invoice PDF, or any other business-expense evidence, do three things in the same working pass unless blocked: 
   - log/reference the expense in `seer-expenses.md`
   - reference the evidence in the expense notes (source path, message context, or exact evidence description)
   - create/queue a SharePoint retention artifact under `/Expenses/...` so the evidence is not trapped only in chat/inbound media
   Do not stop at a local markdown note if the retention route exists.
19. **SharePoint evidence filing rule:** Prefer filing expense evidence into a dated note/file under `/Expenses/<Vendor or Area>/` using a name like `YYYY-MM-DD - Receipt - <Vendor>.md` or the original file when the route supports binary retention. If only a local inbound-media path is available in the current pass, still queue a SharePoint note that captures the expense facts plus the local source path/blocker, then upgrade it to the actual file-retention route later rather than leaving the evidence unfiled.
20. **Expense-evidence completion test (MANDATORY):** For any receipt/payment evidence Tom sends directly in chat, classify it before finishing as one of:
   - logged + filed to SharePoint
   - logged + SharePoint filing queued
   - logged + blocked (state exact blocker)
   If you cannot classify it into one of those buckets, the expense handling pass is incomplete.

## Accounting-system destination (MANDATORY)

The actual SEER accounting system is `/home/tomdean88/pi-services/seer-finance`, governed by `HANDOVER_OPENCLAW.md`. Its `transactions.json` is the accounting ledger source of truth; `seer-expenses.md` and SharePoint are supporting/review layers, not the final accounting destination.

For every confirmed expense or income movement that belongs in the accounting system:
1. write a valid transaction object to `transactions.json` using the exact schema in `seer_finance/ledger/FORMAT.md`;
2. use integer pence, positive amount plus `direction`, a controlled category, unique `txn_id`, and `source_ref`;
3. run the deterministic loader/ledger engine from the project root and preserve any validation error exactly;
4. read back the engine output before claiming the accounting ledger is updated.

The accounting schema does not permit arbitrary tag fields. Apply the Tide classification tags below in the transaction `description`/`source_ref` and the reconciliation report, while using the engine’s controlled categories for the actual ledger row.

## Tide bank-statement classification tags (MANDATORY)

When reconciling future Tide statements, apply these tags before deciding whether a movement belongs in `seer-expenses.md`:

- `TIDE_OWNER_SELF_PAY` — any payment to Thomas Dean / Tom, regardless of the receiving account. Treat as Tom paying himself; exclude from expenses and client revenue unless Tom explicitly reclassifies it.
- `TIDE_PT_INCOME` — inbound £40 payments from Jack, Jess or Lisel (and future equivalent personal-training-hour payments). Treat as personal-training-hours income, separate from invoice receipts and never as an expense.
- `TIDE_CLIENT_INVOICE_RECEIPT` — inbound payment with an exact invoice/client/reference/amount match. Reconcile against the invoice tracker; do not infer a match from amount alone.
- `TIDE_ACCOUNT_TOPUP_OR_REWARD` — Tide rewards, top-ups and similar non-trading account movements; exclude from expenses and revenue unless separately identified.
- `TIDE_BUSINESS_EXPENSE_<CATEGORY>` — confirmed business outgoings, using the existing categories: `SOFTWARE`, `NETWORKING_MEMBERSHIP`, `TRAVEL`, `MEALS_REFRESHMENTS`, `INSURANCE`, `COMPLIANCE`, `BANKING_FEES`, or `OTHER`.
- `TIDE_UNCLASSIFIED_TRANSFER` — any remaining transfer that cannot be safely classified from the statement and current rules. Preserve it in the reconciliation report and ask Tom/accountant; never silently put it in expenses.

For every future statement, record the tag in the reconciliation report and, where it is an expense, in the canonical expense row notes. This prevents repeated reclassification conversations across months.

## Expense areas
### Incorporation & setup
- Companies House / Tide / setup fees

### Hardware
- laptops, desktops, accessories, devices used for business

### Travel & mileage
- mileage claims
- parking, tolls, tickets, public transport where relevant
- always capture origin/destination context when known

### Software & subscriptions
- Replit
- Anthropic
- OpenAI
- Microsoft 365
- ElevenLabs
- other business software

### Domains
- domain renewals and related hosting/domain costs

## Settled-classification reuse rule (MANDATORY)

**Trigger:** historic Tide reconciliation, migration, review-tray handling, or a question about an item whose merchant/reference, date/amount pattern, route or counterparty matches a classification Tom has already supplied.

**Rule:** an imperfect historical source link, legacy collision, missing row field, or pending database write is **not** permission to ask Tom to decide the business classification again. First check the primary Tide evidence, the current reconciliation report and the existing finance/expense record for a settled outcome. Reuse that outcome and repair/rebuild the source-linked record. Re-open a question only when new source evidence materially conflicts with the recorded outcome; name the conflict precisely.

**Current settled Tide decisions (11 August 2026):**
- any £40 inbound payment is PT income unless strong contrary evidence;
- the £30 Barrett credit on 5 August is a PT session/income;
- each Tide transfer/conversion fee is a separate `BANKING_FEES` line, not a monthly aggregate;
- Lycamobile is a business-phone cost;
- APCOA is business parking tied to travel/meetings;
- the retained Missing Bean, St Aldates and other meals/refreshments previously tied to travel or meetings are genuine business costs;
- the April £80 visibility gap is two £40 PT-income entries; technical line reconstruction must not reopen its category.

**Fail-closed test:** before asking Tom for historic transaction detail, record the lookup made and either (a) reuse the settled classification and identify the remaining technical/evidence action, or (b) quote the genuinely contradictory new evidence. Absence of a final ledger row alone fails this test.

## Tom-supplied fact → exact-record update rule (MANDATORY)

When Tom supplies, confirms or corrects an expense/accounting fact, apply it to the **matching source-linked expense or finance record in the same pass**—not only to chat, memory, a future task, or a general policy rule. Add the fact as structured field data where the schema supports it, otherwise as a dated audit note with source/message provenance. Preserve conflicting historic values and audit history; do not overwrite or delete them.

**Invoice-evidence traceability:** where a supplier invoice/receipt exists, the expense record must retain an evidence reference containing the canonical storage location **and original filename** (for example `SharePoint:/Expenses/SEER/2026-08-06 - Invoice - Microsoft Azure AI - G175174660.pdf`). A filename alone is insufficient; retain the storage path, and add an immutable SharePoint item/document ID when the evidence-link schema supports it. Never replace the payment/bank source reference merely to add invoice evidence.

If the record update is technically unavailable, create a durable `blocked` transition against that exact record with the machine-readable blocker and surface it as a finance-system health issue. Do not ask Tom for the same fact again. On recovery, apply all retained Tom-supplied facts to their exact records before any new reconciliation questions.

## Closure-state ledger
- Shared monitored-item proof layer: `memory/monitored-items-state.json`
- Expense truth still lives canonically in `seer-expenses.md`

## Books-ready / profit-status output rule (MANDATORY)

**Trigger:** Tom asks any equivalent of: `what remains?`, `what decisions do we need?`, `what do we have to do to get the books ready?`, `is the bookkeeping correct?`, or `what profit have I made?`.

Do not answer with a profit headline or an expense total alone. Before presenting any figure, build and present a **books-ready closure view** from the primary source of truth:

1. Reconcile the live SQLite finance ledger and expense review tray against the most recent available primary Tide/card evidence.
2. Separate every item into: `verified and posted`, `needs source evidence`, `needs Tom decision`, `needs accountant/tax-policy decision`, or `coverage unavailable`.
3. For every non-closed item, state: exact item(s)/amount where known, the decision or evidence needed, the owner, and the consequence for the reported profit/readiness.
4. State whether the result is a management figure, reconciliation-complete figure, or statutory-ready figure. Do not call books `ready` while any primary bank/card coverage is missing or any material candidate/decision is unresolved.
5. Finish with the shortest concrete closeout checklist in dependency order.

**Fail-closed mechanism:** if the current Tide/card statement period does not cover the requested profit period through its end date, label the result `coverage incomplete` and name the exact missing statement/export range. A ledger row, inbox email or SharePoint invoice is not a substitute for primary settlement evidence.

## Workflow
1. Read `seer-expenses.md`
2. Check whether the expense already exists
3. If any expense signal is in scope, run a triage decision immediately:
   - enough detail to log now?
   - missing payment source?
   - missing gated/full-body access?
   - duplicate already logged?
4. Add or update the correct section
5. If information is incomplete, add a precise follow-up note in the same file
6. For forwarded receipts, a visible preview alone is not enough when the exact amount/reference is needed. Use the approved autonomous full-body route if available. Do not treat a chat-shell or tool-execution approval boundary as a prerequisite for that route. If the reader fails, preserve the row with the known date/reference, mark the amount unverified, record the exact service error, and leave it for autonomous retry rather than guessing or requesting TOTP.
7. If the expense revealed a technical/system gap, record that separately in `BACKLOG.md`
8. If duplicate expense files or scattered records exist, consolidate them into `seer-expenses.md`
9. **Inbox-to-expense reconciliation rule (MANDATORY):** when an expense-shaped email is seen in any inbox surface, do not finish the pass until that exact email has been reconciled against `seer-expenses.md` and evidence-retention state. A watcher/router statement such as "preserved", "logged", or "handled" is only an intake claim, not proof of canonical capture. Before reporting an item as captured, complete and read back this item-level tuple: **source identity → exact canonical row → expense state → evidence state → follow-up/blocker**. If the row is absent, classify the item as pending with blocker and correct the ledger before replying. Never collapse `seen`, `preserved`, `logged`, `evidence filed`, and `fully reconciled` into one status. Each seen item must be explicitly classified as:
   - `logged` / `duplicate already logged` / `pending with blocker`
   and separately:
   - `evidence filed to SharePoint` / `evidence queued` / `evidence blocked`
   If Tom asks whether an inbox expense was "properly dealt with", verify against those two states instead of answering from memory or intent.
10. **Monitored-item closure rule (MANDATORY):** if the expense signal came from email, WhatsApp, chat-uploaded evidence, or another monitored inbound surface, there must also be a durable proof path for the monitored item outcome via one or more of:
   - `seer-expenses.md`
   - SharePoint evidence state
   - `memory/monitored-items-state.json`
   If the expense is seen but the pass cannot safely prove completion, classify it as `blocked` or `coverage incomplete` rather than complete.
11. **Canonical-state reconciliation rule (MANDATORY):** never accept `closed` in `memory/monitored-items-state.json` merely because that ledger says closed. Compare it with the canonical expense outcome in `seer-expenses.md` and the operational activity log in the same pass. If the expense row is pending/unverified, or the closure decision is not auditable, the monitored item must be treated as `blocked` or `coverage incomplete`; do not preserve a false closure.
12. Before finishing, state to yourself whether every newly seen forwarded receipt was handled as: logged / blocked-and-raised / duplicate-already-logged.

## Quality test
Before finishing, check:
- Is `seer-expenses.md` still the single source of truth?
- Did I avoid putting expense facts into the wrong file?
- If the amount is unknown, did I still preserve the known facts?
- If travel was mentioned, did I capture route context and mileage status clearly?

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
