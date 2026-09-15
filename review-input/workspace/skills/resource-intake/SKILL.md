---
name: resource-intake
last_edited: 2026-06-10 15:33
description: Intake and retain reusable transcripts, documents, notes, research dumps, and other shared materials in the correct canonical home with useful metadata.
---

# Resource Intake

## Purpose
Do not let important uploaded or pasted material vanish into chat history.

When Tom shares a transcript, document, prep pack, notes dump, or long conversation, your job is to:
1. decide what type of resource it is
2. retain it in a durable place
3. capture a concise useful summary
4. make later retrieval easier

## Mandatory retention rule
If Tom uploads a transcript or transcript-like resource, retain it by default.
Do not treat it as temporary chat context unless Tom clearly says not to keep it.
If Tom wants it kept, preserve the **full original text/body**, not just a summary or extracted notes.

### Financial-source retention rule (MANDATORY)
Bank statements, bank transaction exports, invoices, receipts and accounting evidence are **high-integrity primary sources**, not disposable chat attachments. Before using them for reconciliation or accounting claims:
1. retain the original file unchanged under `reference/finance/source-statements/<institution>/<YYYY>/` (or the named financial-evidence equivalent);
2. record filename, received timestamp, coverage period, original-source channel and SHA-256 in a companion `README.md` or intake record;
3. read back the stored file and verify its checksum before reporting retention complete;
4. keep derived extracts, reconciliation reports and ledger entries explicitly linked to that primary-source record;
5. never claim a financial reconciliation is source-complete if the original statement/export is absent—label it `coverage incomplete`.

For multiple statements, preserve every original file; never replace a statement with an extracted summary. Duplication is preferable to loss. If a local write is blocked, immediately report the exact blocker and retain no false claim that the source was saved.

## Classification check (MANDATORY)
Before responding, classify the material into one of these:
1. **Immediate-use only** — needed for the current task, but not worth durable storage
2. **Reusable knowledge resource** — worth keeping for later reference/synthesis
3. **Entity-specific context** — belongs to a CRM/legal/career/person/project context
4. **Ambiguous** — unclear where it belongs

If ambiguous, ask before filing.

## Routing rules
### A. Reusable knowledge resource
Use this when the material is general reference value rather than tied tightly to one entity.
Store as a resource note under:
- `reference/transcripts/YYYY-MM-DD - <descriptive-title>.md`

Include:
- received date
- source / filename if relevant
- short useful summary
- key takeaways
- raw transcript/source note if helpful

### B. Entity-specific context
Use this when the material clearly belongs to a person/company/opportunity/legal matter/interview thread/project.
Examples:
- CRM/account/opportunity context
- legal correspondence / dispute material
- interview prep tied to a company/role
- project-specific notes

Store in the governing system for that entity where possible, or create a durable reference note that clearly names the entity and purpose.
If there is an applicable governing skill (CRM, SharePoint, transcript-resource, etc.), use it.

**Operational transcript rule (MANDATORY):** if Tom shares a substantive meeting transcript tied to a live entity, do not stop at asking where to file it if the likely home is already inferable. First:
1. identify the entity
2. read/understand the transcript
3. extract decisions, follow-ups, and task implications
4. update the governing systems (for example CRM / TASKS / SharePoint path)
5. ask clarifying questions only for details that are genuinely blocking safe capture

Fail-closed test: if Tom could reasonably expect "understand this and update everything accordingly", do that first instead of bouncing the work back as a filing-choice question.

### C. Immediate-use only
Use this only when the material is genuinely disposable and Tom has not asked to retain it.
If there is any realistic chance it will matter later, prefer retention.

## Decision hierarchy
1. Tom's explicit instruction
2. Clear entity linkage
3. Reusability value
4. If still unclear, ask

## Summary standard
Every retained resource should make later reuse easier.
Capture:
- what it is
- why it matters
- what future task it might help with
- any important dates / people / companies

## Exact-line retention and retrieval rule (MANDATORY)
When Tom explicitly says some wording/notes/phrases should be **stored for later**, and the material includes a line that may later be reused verbatim (for example: positioning copy, a bio line, a tagline, a pitch sentence, a talk phrase, or a preferred formulation), you must preserve that wording in a way that is easy to retrieve exactly later.

Required mechanism:
1. Store the exact line verbatim in the retained resource note under a clearly labelled section.
2. If the line is likely to matter beyond the single note, also include a short retrieval cue such as `Preferred wording`, `Exact line to reuse`, or equivalent.
3. When Tom later asks whether a line was saved, stored, or kept — or asks for the exact wording back — do **not** answer from memory or semantic guesswork first.
4. First check the actual retained destination file(s) directly.
5. If a retained file exists, treat that file as the primary source of truth over memory search results.
6. If you have not checked the retained file yet, fail closed: say you need to verify the stored note rather than saying it was not saved.

Fail-closed test:
- If Tom can show a screenshot of you saying "stored for later here", you must never answer "I couldn't find it" until you have checked that exact stored file.

## Source-inspection integrity rule (MANDATORY)
If Tom asks for themes, clips, quotes, or ideas **from a specific uploaded file/transcript/document**, do not answer as if you have reviewed the source unless you have actually read or extracted the file contents.

Allowed responses when the source content has **not** been inspected:
- say you are inferring only from surrounding context / prior notes
- ask for the file in a readable form
- or state that you need the gate/access/tool path required to inspect it properly

Not allowed:
- presenting inferred themes as if they came from the file itself
- implying you reviewed the upload when you only used chat context or a stored summary note

## Owning-system completion rule (MANDATORY)
If the retained material materially changes the truth of another governed system, do not stop at filing.
Complete the owning-system update in the same pass when evidence and access are sufficient.

Examples:
- client/prospect meeting material -> CRM + SharePoint updated if the content changes status, next step, or understanding
- invoice/expense evidence -> owning invoice/expense system updated or explicitly blocked
- project/operational pack -> relevant task/reference/project truth updated if the content changes live state

## Proof rule (MANDATORY)
If this skill performs meaningful retention or downstream truth maintenance, leave a reviewable proof path via one or more of:
- stored artifact path
- destination system of truth
- `reference/OPERATIONAL_ACTIVITY_LOG.md`
- `memory/monitored-items-state.json` when the source came from a monitored inbound surface

## Ambiguity / ask-Tom rule (MANDATORY)
If you are not materially certain what the material is, who it belongs to, where it should be retained, or what downstream system should be updated, ask Tom a short clarification question instead of guessing.

## Fail-closed rule
If Tom says or clearly implies that the material should be kept, do not leave it unfiled.
Retention first, discussion second.

## Examples
- Uploaded interview prep doc for a named company → retain as interview resource
- Pasted conversation transcript with Mike/George about AI → retain as reusable transcript resource unless Tom wants it attached to a specific project
- Solicitor letter about BCN → retain as legal/entity-specific resource
- Long workshop transcript for a client → entity-specific context, not a generic note

## If unknown
Ask one focused question about destination/classification rather than guessing.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".