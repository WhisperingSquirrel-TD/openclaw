---
name: invoice-create
description: Create a new invoice tracker line after researching billing details, presenting a dry-run proposal, resolving ambiguity, and passing the required creation gate.
---

# Invoice Create

## Goal
Create a correct new row in the SharePoint `Invoice tracker` list without guessing critical billing details.

## Workflow
1. Identify the exact client/entity.
2. Research billing details from local sources first:
   - `stackstone/crm.md`
   - SharePoint account/opportunity context
   - `contacts.md`
3. Try to resolve or confirm:
   - legal/client entity name
   - invoicing/accounts email (read from account Current + contacts + prior invoices; do not guess from memory)
   - contact person
   - office/billing address if relevant to the invoice workflow
   - work description / basis for billing
   - issue date / due date / amount
4. Before asking Tom for missing invoice-detail fields like address, billing email, or contact details, search the live local context first:
   - `stackstone/crm.md`
   - the entity's SharePoint cache folder / `Current.md`
   - prior invoice files / prior invoice communication artifacts
   - `contacts.md`
   Only ask Tom once those sources have been checked and the detail is still missing or ambiguous.
5. If a critical billing field is missing or ambiguous after those checks, ask Tom rather than guessing.
6. Produce a dry-run proposal first whenever the row is consequential or context-derived.
7. Use the invoice ops command layer for the actual row create.
8. Do all possible ungated preparation first: entity resolution, document reading, billing-detail extraction, duplicate checking, and dry-run proposal.
9. Only perform the create when the gate/TOTP approval is open and the next step is the actual row write.

## Critical rules
- Do not invent billing or legal details.
- Do not assume the first email found is definitely the right invoicing email if the context suggests a finance/accounts address may differ.
- If Tom says things like "current Harken work", use context resolution first; if confidence is low, surface the ambiguity.
- Prefer storing enough context in `Notes` so later chasing/closure makes sense.
- **Completion-not-detection rule (MANDATORY):** this skill is not complete when an invoice row is merely proposed. Completion means the row was actually created, detected as already existing, or failed closed with the exact blocker.
- **Ambiguity / ask-Tom rule (MANDATORY):** if client/entity identity, billing recipient, amount, due-date logic, or row targeting is materially uncertain after source checks, ask Tom instead of guessing.
- **Operational activity logging rule (MANDATORY):** when a new invoice row is created, detected as already existing, or blocked on missing data/gate state, record the meaningful outcome in `reference/OPERATIONAL_ACTIVITY_LOG.md` so Tom can review whether the invoice pathway was actually handled.

## Command layer
Use:
- `python3 ~/.openclaw/integrations/microsoft-l1/invoice_ops.py create ...`
- `python3 ~/.openclaw/integrations/microsoft-l1/invoice_ops.py create-from-context ...`

## Minimum dry-run output
Show:
- target client/entity
- proposed fields
- any assumptions made
- any unresolved gaps requiring Tom

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
