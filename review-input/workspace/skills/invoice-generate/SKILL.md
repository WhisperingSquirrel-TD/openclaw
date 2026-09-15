---
name: invoice-generate
description: Generate branded Stackstone invoice files from structured data, using the approved HTML-to-PDF route, storage rules, and tracker linkage.
last_updated: 2026-05-25 14:28
---

# Invoice Generate

## Goal
Create a branded invoice file (PDF first) from structured invoice data, using the Stackstone branding and format.

## Quick Start (Two Scenarios)

**If Tom created a tracker row already:**
1. Find the row: `invoice_ops.py find --client "Name"`
2. Use the invoice number from that row (remove "DRAFT-" if present)
3. Generate JSON with details from tracker + previous invoices
4. Generate PDF using that number
5. **After sending: update tracker with "Sent" status + link**

**If creating a new invoice from scratch:**
1. Check highest invoice number: `invoice_ops.py list --top 10`
2. Increment by 1
3. Create tracker row if Tom asks
4. Generate PDF with new number
5. **After sending: update tracker with "Sent" status + link**

## The Invoice Generator Script
**Location:** `~/.openclaw/integrations/microsoft-l1/invoice_generate.py`

This is the ONLY invoice generation script to use. It handles:
- Stackstone branded HTML generation with correct logo/colors
- PDF rendering via Chromium
- SharePoint upload to client Finance folder
- Invoice tracker link updates
- Optional email sending

## Pre-Generation: Invoice Number and Tracker Check (MANDATORY)

**Before generating any invoice, determine the workflow:**

### Scenario 1: Tom created a tracker row (most common)
Tom may have already created an invoice row with an assigned number (e.g., "DRAFT-INV-073" or "INV-075").

**Steps:**
1. Check if tracker row exists for this client/work:
   ```bash
   python3 ~/.openclaw/integrations/microsoft-l1/invoice_ops.py find --client "Client Name"
   ```
2. If row exists with invoice number → **use that number** (remove "DRAFT-" prefix if present)
3. Pull client details, amount, dates from the tracker row
4. Generate invoice using the assigned number

**Rule:** If Tom created a tracker row, he assigned the invoice number. Use it, don't guess or increment.

### Scenario 2: Creating a new invoice (Tom asks you to create the row)
Tom explicitly asks you to create a new invoice row.

**Steps:**
1. List recent tracker items to find highest invoice number:
   ```bash
   python3 ~/.openclaw/integrations/microsoft-l1/invoice_ops.py list --top 10
   ```
2. Increment by 1 for the new invoice number
3. Create tracker row first (if Tom asks), then generate PDF

**Source of truth hierarchy:**
1. **Live SharePoint Invoice tracker** (primary) - invoice number, title, client, amount, issue date, due date, status, and chase fields all come from the exact live row
2. Previous invoices in SharePoint cache (secondary) - static client details only, and only if the live row lacks them
3. Never guess invoice numbers or transactional fields

**Mandatory live-row copy and timezone rule:** before every new generation, correction, or regeneration, run `invoice_ops.py find` and select the exact invoice row. Use the row's title, invoice number, client, amount, and status from the live row. Treat tracker ISO timestamps with `Z` as UTC and convert `issue_date` and `due_date` to `Europe/London` before writing the invoice payload's display dates; never copy the UTC date component directly. Do not reuse earlier proposals, chat-confirmed assumptions, stale local mirrors, or dates from a previous payload. If the exact row or a required field cannot be resolved, stop and fail closed.

**Mandatory post-generation verification:** extract text from the generated PDF and compare the invoice number, exact title, amount, and displayed issue/due dates against the selected live tracker row after the same explicit `UTC → Europe/London` conversion. A mismatch is an incomplete generation: do not claim completion or leave the wrong PDF as the final artifact.

**Test before generating:** "Do I know every transactional field from the exact live tracker row, or am I guessing?" If guessing, check the live tracker first.

## Workflow
1. **Create invoice payload JSON** with this exact structure:
```json
{
  "business": {
    "registered_name": "SEER Innovations Ltd",
    "trading_name": "Stackstone Consulting",
    "company_number": "17100455",
    "address_lines": [
      "21 St John's Road",
      "Abingdon",
      "OX14 2HA"
    ],
    "email": "Tom@stackstoneconsulting.co.uk",
    "phone": "+44 7894 241 276"
  },
  "client": {
    "name": "Client Name",
    "address_lines": [
      "Address line 1",
      "Address line 2",
      "Postcode"
    ],
    "email": "client@example.com",
    "phone": "+44 1234 567890"
  },
  "invoice": {
    "reference": "INV-0075",
    "amount_due": 1200.00,
    "due_date": "08/06/2026",
    "issue_date": "25/05/2026"
  },
  "line_items": [
    {
      "description": "Half day onsite and report",
      "qty": 1,
      "unit_cost": 1200.00,
      "amount": 1200.00
    }
  ],
  "payment": {
    "account_name": "SEER Innovations Ltd",
    "account_number": "30855597",
    "sort_code": "04-06-05"
  }
}
```

2. **Save the JSON** to a temp file, e.g., `/tmp/invoice-075.json`

3. **Run the generator script:**
```bash
python3 ~/.openclaw/integrations/microsoft-l1/invoice_generate.py \
  --input-json /tmp/invoice-075.json \
  --sharepoint-path "/Accounts/Client Name/Finance/2026-05-25 - Invoice - INV-075.pdf" \
  --update-tracker \
  --tracker-invoice-number "INV-0075"
```

The script will:
- Generate HTML with Stackstone branding (logo from `~/.openclaw/workspace/stackstone/brand/logo-horizontal.svg`)
- Render PDF via Chromium
- Upload PDF to SharePoint at the specified path
- Update Invoice tracker row with the file link

4. **Preflight check is built into the script** - it validates:
   - registered business name present
   - trading name present
   - invoice reference present
   - company number present

5. **Output** is JSON with paths and SharePoint URL

## Value-based line item descriptions (MANDATORY)
Tom is moving away from day-rate language toward value deliverables. When writing line item descriptions:

**❌ Avoid day-rate language:**
- "Onsite and report - 1 day"
- "Consultancy services - 1.5 days"
- "2 days consulting"

**✓ Use value-based deliverable language:**
- "Half day onsite and report"
- "Onsite session and report"
- "Discovery session and recommendations"
- "Consultancy services - 1.5 days" → becomes "Consultancy services" or more specific deliverable

**Rule:** Describe WHAT was delivered, not HOW LONG it took. If Tom provides day-count context during invoice creation, convert it to a deliverable description before generating.

## Two modes of operation

**Mode A: Using an existing tracker row (common)**
- Tom created the tracker row already
- Row has assigned invoice number (may have "DRAFT-" prefix)
- Your job: generate the PDF using that number
- Command: `invoice_ops.py find --client "Name"` to locate the row

**Mode B: Creating a new invoice from scratch (Tom explicitly asks)**
- Tom asks you to create a new invoice row
- Check tracker for highest number first: `invoice_ops.py list --top 10`
- Increment by 1
- Create row if requested, then generate PDF

## Finding client details
Before generating, check in this order:
1. **Invoice tracker row** (if it exists) - may have client email, account email, notes
2. Previous invoices in SharePoint cache for that client (use existing address/email only)
3. `contacts.md` for contact details
4. CRM files for company/contact info
5. If registered address needed and not in files, use web search to check Companies House

## Reusing previous invoice details (MANDATORY)
When Tom says "use the details from the last/previous invoice", treat that as **static client-detail reuse only**, not full invoice-template reuse.

**Reusable from a previous invoice:**
- client name / billing name
- postal address
- client email
- client phone/contact details
- stable business/bank details if still current

**Never copy from a previous invoice unless Tom explicitly says to:**
- invoice number/reference
- issue date
- sent date
- due date
- amount/total
- line-item quantity/day count
- invoice status
- paid/chased/auto-chase state
- notes about payment or prior communications
- SharePoint filename/path date

**Fresh transaction-date rule:**
- If Tom asks for a new invoice and does not specify a send date, assume he intends to send it the same day.
- Set the invoice issue/sent basis to today’s date.
- Set the due date to **at least 14 days after the assumed send/issue date** unless Tom specifies different terms.
- If the tracker row date fields are blank, fill them from this fresh-date rule; do not leave them blank just because the tracker row was only a draft.

**Field-split checklist before generation:**
Before generating any invoice from a previous invoice, write the payload/source split to yourself:
1. New tracker row supplies invoice number, client, amount/title where present.
2. Previous invoice supplies only reusable client/contact/address details.
3. Current/fresh transaction context supplies issue/sent basis, due date, status assumptions, SharePoint filename date, and new line-item wording.


**Note:** Current tracker schema has client email fields but not full postal address. You'll still need to look up addresses from previous invoices or Companies House.

**Example Companies House search:**
```
"Company Name Ltd" site:find-and-update.company-information.service.gov.uk
```

## Critical rules
- **Always use `invoice_generate.py`** - never improvise a new script
- The script uses the Stackstone brand colors and logo automatically
- SharePoint path format: `/Accounts/{Client Name}/Finance/{YYYY-MM-DD} - Invoice - {INV-XXX}.pdf`
- Invoice tracker update requires `--update-tracker` flag plus either `--tracker-invoice-number` or `--tracker-item-id`
- The script handles PDF generation, SharePoint upload, and tracker updates in one run
- If critical fields are missing from the JSON, the script will fail - fix the JSON before retrying
- **If tracker row doesn't exist yet:** generate without `--update-tracker`, then create/update row separately
- **Completion-not-detection rule (MANDATORY):** this skill is not complete when the payload or PDF is merely prepared. Completion means the PDF exists in the intended retention home and the relevant tracker state is updated, or the pass failed closed with the exact blocker.
- **Ambiguity / ask-Tom rule (MANDATORY):** if invoice number source, client identity, billing details, storage path, or send-vs-generate intent is materially uncertain, ask Tom instead of guessing.
- **Gate-retry rule (MANDATORY):** if a TOTP-gated invoice generation command is denied and Tom says the gate is open, retry the exact command once immediately before replying that the gate is still blocking. Treat the second live exec result as the source of truth, not the earlier denial.
- **Operational activity logging rule (MANDATORY):** every meaningful invoice-generation state transition must be logged to `reference/OPERATIONAL_ACTIVITY_LOG.md` with the invoice number, trigger/source, action taken, state (`Confirmed` / `Blocked` / `Coverage incomplete`), and proof/source. If the PDF is generated and stored but the local tracker mirror lags, log that lag explicitly rather than implying the mirrors are already aligned.
- **Bundled CRM + invoice status rule (MANDATORY):** when an invoice-generation request arrives inside a multi-part client update, convert the user request into an explicit checklist before the final reply: (1) adjacent CRM/contact updates captured, (2) invoice tracker row found/used, (3) PDF generated and stored, (4) tracker link/status updated, (5) SharePoint link returned. Do not answer with generic "processed"/"logged" wording unless every item is complete. If TOTP or another gate blocks generation, state exactly which checklist items are done and which invoice items remain blocked.

## Optional flags
- `--send-email` - send invoice as email attachment
- `--recipient-email` - override client email from JSON
- `--cc-email` - add CC recipient
- `--mark-sent` - update tracker status to "Sent" after emailing

## After generation: sending the invoice
**MANDATORY:** When Tom asks to send an invoice just generated:
1. Use the email-send skill (read it first)
2. Attach the PDF from `/tmp/INV-XXX.pdf`
3. **NEVER include SharePoint links in external client emails** - clients cannot access SharePoint
4. Prepare all /tmp files BEFORE showing draft (recipients, subject, body)
5. Simple email: "Please find attached invoice INV-XXX for £X.XX for [deliverable]. It is due on [date]."

## After sending: update the tracker (MANDATORY)
**CRITICAL:** Once an invoice is sent (by you OR by Tom), the tracker MUST be updated immediately.

**Two-layer control (MANDATORY):**
1. **Primary control:** update the tracker in the same send window
2. **Backstop control:** if a later sent-mail review, inbox-check, or invoice-status review finds invoice-send evidence but the tracker was not updated correctly, repair the tracker immediately rather than assuming the send workflow already handled it

The job is not complete until both controls are true in practice.

**When this applies:**
- After you send an invoice via email-send
- When Tom mentions he sent an invoice
- When you spot an outbound invoice in email-check
- When an outbox/sent mirror or other send-evidence surface shows the invoice was sent

**Send-evidence reconciliation rule (MANDATORY):**
Any time there is credible evidence that an invoice has actually been sent, do not assume the tracker has already moved out of Draft or that chase state is scheduled correctly.

Required mechanism:
1. Resolve the exact invoice row under the live invoice number.
2. Verify the tracker no longer effectively sits in draft state (`Draft`, `DRAFT-INV-*`, or equivalent unsent state).
3. Verify/update `Status` to `Sent` (or `Overdue` if already past due when reconciled).
4. Verify/update `issue_date`, `due_date`, and `invoice link` from the best available source of truth.
5. Verify that chase-driving state exists after send — at minimum the tracker must carry the next chase/review point it will use (for the current schema this is typically `next_chase_date`, usually aligned to due date unless Tom specifies otherwise).
6. If any of those fields cannot be verified or repaired safely in the same pass, fail closed: say the invoice was sent but tracker/chase reconciliation is still incomplete or blocked.

**No-assumed-sent-completion rule (MANDATORY):**
Do not answer a question like "did you mark it as not draft anymore and schedule a chase?" from memory, generation-time assumptions, or because the PDF/link update succeeded earlier. Re-read or live-check the tracker row after send evidence before claiming the reconciliation is complete.

**Required tracker updates:**
1. **Status:** "Sent" (or "Overdue" if already past due date when sent)
2. **Issue date:** must be populated
3. **Due date:** must be populated
4. **Invoice link:** SharePoint URL from generation output (if not already set)
5. **Notes:** Append send confirmation: "Sent to [client] on [YYYY-MM-DD] from assistant@" (or "from tom@" if Tom sent it)
6. **Last chased:** Can be left empty on first send (this is for chase reminders)

**Invoice-date completeness rule (MANDATORY):**
A sent invoice row is not complete if `issue_date` or `due_date` is blank.
Do not treat `Status: Sent` as sufficient on its own.

Required mechanism:
1. After any invoice send, verify that the tracker row has both `issue_date` and `due_date` populated.
2. If either is blank, repair the row immediately from the best available source of truth:
   - generated invoice payload / PDF
   - outbound send date
   - Tom-confirmed payment terms
3. If the correct due date cannot be verified safely, fail closed: mark the invoice tracking state as incomplete and tell Tom the row still needs completion.
4. Do not leave a sent invoice in a state that prevents due/overdue review logic from working.

**Command:**
```bash
python3 ~/.openclaw/integrations/microsoft-l1/invoice_ops.py update \
  --invoice-number "INV-XXX" \
  --status "Sent" \
  --invoice-link "https://seerepeat.sharepoint.com/.../INV-XXX.pdf" \
  --notes "Sent to [client] on 2026-05-25 from assistant@"
```

**Test before claiming done:** "If Tom asks tomorrow 'did we send invoice X?', can the tracker answer definitively?" If no, update incomplete.

**Integration with email-check / sent-mail review:**
When checking sent items, if you see an invoice email (subject contains "Invoice INV-" or attachment is an invoice PDF):
1. If the mirrored feed does not expose enough detail to verify the send, escalate immediately to live mailbox access / TOTP rather than guessing from the mirror
2. Extract invoice number
3. Check whether the tracker row exists under the exact live identifier (including catching cases like `DRAFT-INV-073` that should have become `INV-073`)
4. Verify that tracker status reflects reality (`Sent`, `Paid`, or `Overdue` as appropriate), that notes record the send, **and that issue/due dates are populated**
5. If tracker state is stale, inconsistent, still Draft, or missing issue/due dates, update it immediately
6. If the invoice identifier itself is inconsistent, flag that explicitly and normalise it when safe rather than leaving future lookups to fail silently

**Invoice-review fail-closed rule (MANDATORY):**
If an invoice review finds a row with invoice-send evidence but missing `issue_date` or `due_date`, do not report "nothing due/overdue" as if the system is healthy.
Instead, surface the row as an **incomplete tracker item** that must be repaired before the review can be trusted.

## Example full command
```bash
python3 ~/.openclaw/integrations/microsoft-l1/invoice_generate.py \
  --input-json /tmp/inv-075-andy-barrett.json \
  --sharepoint-path "/Accounts/Andy Barrett - SJP/Finance/2026-05-25 - Invoice - INV-075.pdf" \
  --update-tracker \
  --tracker-invoice-number "INV-0075"
```

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
