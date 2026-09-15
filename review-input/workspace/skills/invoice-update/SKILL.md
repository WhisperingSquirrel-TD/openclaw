---
name: invoice-update
description: Safely update an existing invoice tracker line with a reviewed field diff covering status, amounts, dates, notes, or links.
---

# Invoice Update

## Goal
Safely update the correct invoice row without mutating the wrong item.

## Live destination-truth rule (MANDATORY)
`INVOICE_TRACKER.md` is a convenience mirror, not proof of the current destination state. For every invoice-status question or sent-item reconciliation, use `invoice_ops.py find --invoice-number <INV-NNN>` (or `list`) first; treat its live SharePoint/API result as authoritative. Use the markdown mirror only as a secondary comparison, and label it stale if it contradicts the live result. After any mutation, read back the live row and record any mirror lag as `coverage_incomplete` rather than allowing the stale mirror to suppress the update.

## Workflow
1. Resolve the target invoice by:
   - invoice number first when available
   - otherwise a unique client/item match
2. Read the current row summary.
3. Build the intended field changes explicitly.
4. Use dry-run when the change is non-trivial.
5. Apply the update only when the gate/TOTP approval is open.
6. Read back the row after update where possible.

## Critical rules
- Selector fields and mutation fields must stay separate.
- Do not update an ambiguous target.
- If multiple rows match, stop and show the matches.
- Preserve useful operational notes when the update changes invoice state materially.
- **Completion-not-detection rule (MANDATORY):** if evidence shows an invoice state should change (for example sent, chased, paid-signal-adjacent, link/status/date changes), do not stop at reporting that evidence. First surface the exact tracker delta that should now exist (status/date/notes/chase-field implications), then update the relevant tracker rows/fields when evidence and access are sufficient, or fail closed with the exact blocker.
- **Mirror-sent trigger rule (MANDATORY):** sent/outbox mirror evidence is sufficient to trigger this skill. If an email mirror shows that an invoice, reminder, or chase was sent, reconcile the tracker row immediately for sent-state fields (for example status, sent date, notes, chase-driving state) rather than assuming some other workflow already did it.
- **TOTP-escalation rule (MANDATORY):** if the invoice row should be changed but the tracker cannot be updated from the current access route, ask Tom for TOTP/gate immediately rather than stopping at diagnosis.
- **Ambiguity / ask-Tom rule (MANDATORY):** if you are not materially certain which invoice row is correct or which fields should change, ask Tom instead of inferring.
- **Operational activity logging rule (MANDATORY):** when an invoice row is materially updated (status, dates, links, amount, notes, chase-driving fields), write the outcome to `reference/OPERATIONAL_ACTIVITY_LOG.md` with invoice number, action taken, resulting state, and proof/source.

## Command layer
Use:
- `python3 ~/.openclaw/integrations/microsoft-l1/invoice_ops.py update ...`

## Minimum dry-run output
Show:
- resolved target row
- proposed field diff
- any ambiguity or conflict

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
