---
name: invoice-chase
description: Chase unpaid invoices from assistant@ using the approved reminder workflow, review gate, send controls, and post-send tracker update.
---

# Invoice Chase

## Goal
Send a polite invoice reminder from `assistant@` and keep the SharePoint row current.

## Execution rule (MANDATORY)
When Tom asks to "walk through the steps", "prepare a chase", or "show me how you'd chase invoice X", treat that as a command to **execute this skill's workflow using real data**, not to explain the process in theory. Enter this skill immediately, read the live tracker + account context, and only then propose output. Do not guess, assume, or freelance from memory.

## Workflow
1. Resolve the exact invoice row.
2. **Verify the recipient email from live data** (MANDATORY):
   - Read the tracker row for the target invoice
   - If the row's client email field is present and looks like a billing/accounts email, use that
   - If the row's client email is a personal contact or ambiguous, cross-check account Current file + contacts.md for the correct billing/accounts recipient
   - Do not propose a recipient from memory or assumption alone
   - Fail-closed rule: if the correct billing email cannot be confidently identified from available data, ask Tom before drafting
3. Check guardrails before any send:
   - not Paid
   - not Hold
   - auto chase not disabled
   - usable client email exists
   - not recently chased unless Tom explicitly forces it
3. Draft the reminder email.
4. Prefer dry-run first, especially for real client sends.
5. Do all possible ungated preparation first: target resolution, guardrail checks, recipient validation, subject/body drafting, and intended row changes.
6. Only send when the gate/TOTP approval is open and the next step is the actual send.
7. After send, update the row with the relevant workflow-driving fields/rows for that chase event, including as appropriate:
   - last chased
   - next chase date if appropriate
   - notes
   - due-date-aware status logic
   - any other chase-driving metadata the tracker uses to govern future behavior
8. Read back the updated row if possible.

## Template/tone rules
- Use a polite assistant/back-office tone from `assistant@`.
- Distinguish between not-yet-due and overdue invoices in the copy.
- Do not make the reminder more aggressive than the situation requires.
- If the invoice is not yet due, treat it as a gentle prompt, not a debt-collection email.

## Critical rules
- Never bypass guardrails silently.
- If blocked, say exactly why.
- Do not chase again in a tight window unless explicitly forced.
- Keep the relationship clean; this is an admin nudge, not a commercial escalation.
- **Completion-not-detection rule (MANDATORY):** a chase is not complete when the email is merely drafted or sent. The owning tracker must also reflect the chase event, or the result must be explicitly blocked with the reason.
- **Ambiguity / ask-Tom rule (MANDATORY):** if recipient, target invoice, or correct chase state is materially uncertain, ask Tom instead of guessing.
- **Operational activity logging rule (MANDATORY):** every chase dry-run, send, block, or tracker follow-up state transition that Tom may later want to audit must be logged to `reference/OPERATIONAL_ACTIVITY_LOG.md` with invoice number, recipient, action state, and proof/source.

## Command layer
Use:
- `python3 ~/.openclaw/integrations/microsoft-l1/invoice_ops.py chase ... --dry-run`
- `python3 ~/.openclaw/integrations/microsoft-l1/invoice_ops.py chase ... --send`

## Minimum dry-run output
Show:
- target invoice summary
- guardrail result
- recipient
- subject
- body
- intended post-send row changes

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
