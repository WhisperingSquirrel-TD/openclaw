---
name: invoice-close
description: Close an invoice tracker line after payment, settlement, write-off, or final resolution, recording the outcome and stopping further chase activity.
---

# Invoice Close

## Goal
Mark an invoice as no longer requiring active chasing and capture the final settlement state cleanly.

## Workflow
1. Resolve the exact invoice row.
2. Determine the closure type:
   - paid
   - part-paid
   - hold / manual handling
   - no further chasing needed
3. Prepare the field update.
4. Capture useful closure details where available:
   - paid date
   - settlement note
   - exception note if not straightforward
5. **Build structured field changes, not note-only closure:**
   - set `status` appropriately (normally `Paid`)
   - set the actual `paid_date` / Paid column when payment is confirmed
   - clear or neutralise chase-driving fields if they would otherwise imply more chasing
   - add notes as supporting evidence, not as a substitute for updating the real columns
6. Apply the update only when the gate/TOTP approval is open.
7. Read back the row after update where possible.
8. **Close it off the watch list:** append a short resolution line to `ACTIONED.md` when the payment confirmation came from a message/watch flow that could otherwise resurface.

## Payment-confirmation trigger (MANDATORY)
If there is credible payment evidence for an invoice — including Tom reporting it directly, a client/contact message, email, WhatsApp, bank/payment reference, or other reliable confirmation — treat that as the trigger to run this skill.

This explicitly includes **sent/outbox mirror evidence** such as Tom emailing a client to say thank you for payment or otherwise acknowledging that the invoice has been paid.

**Default next step:**
- tell Tom payment is confirmed
- explicitly surface the exact tracker state change that should happen (for example `INV-076 should move to Paid with paid date 2026-06-30`)
- ask for gate/TOTP if needed
- mark the invoice Paid in the tracker

Do not first ask Tom whether you should verify the payment claim unless the evidence itself is ambiguous or unreliable.

## Critical rules
- Do not mark the wrong invoice paid.
- If the payment evidence is unclear, ask Tom.
- Closing the row should stop future chase behavior.
- **Structured-columns rule (MANDATORY):** never treat "put it in the notes" as sufficient for a payment/closure update. If payment is confirmed, the actual tracker columns must reflect it — especially `Status` and `Paid` / `paid_date` where those fields exist.
- **TOTP-escalation rule (MANDATORY):** if payment evidence is credible but the tracker cannot be updated from the current route, ask Tom for TOTP/gate immediately so the row can actually be closed.
- **Read-back rule (MANDATORY):** after marking an invoice paid, verify that the mirror/readback shows the structured payment fields populated. If the notes mention payment but the Paid column is still blank, the closure is incomplete.
- **Watch-list cleanup rule:** if the payment evidence came from inbox/WhatsApp/watch monitoring, do not stop at updating the tracker. Also record the closure in `ACTIONED.md` so repeated watch passes suppress it.
- **Operational activity logging rule (MANDATORY):** when an invoice is marked paid, held, part-paid, or otherwise closed, write that closure state to `reference/OPERATIONAL_ACTIVITY_LOG.md` with invoice number, trigger/source, resulting tracker state, and proof/source.

## Command layer
Use:
- `python3 ~/.openclaw/integrations/microsoft-l1/invoice_ops.py update ...`

## Minimum dry-run output
Show:
- resolved target row
- intended closure fields
- any missing settlement details

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
