---
name: bootstrap-governance
description: Audit or restructure bootstrap/context files such as AGENTS.md, MEMORY.md, SYSTEM_MAP.md, USER.md, or HEARTBEAT.md without unnecessary duplication or context growth.
---

# Bootstrap Governance

Use this skill when the job is not just "edit a file", but "protect the bootstrap layer".

Bootstrap files are unusually expensive and unusually important because they shape session behaviour before domain skills even start. The goal is to keep them **light, sharp, and reliable**.

## Core principle
Bootstrap files should contain:
- routing triggers
- compact decision rules
- high-value durable context
- small amounts of information that truly must be present early

### Permanent admission rule — prevent backflow
A rule or detail must not be added to `AGENTS.md` merely because it is important, safety-related, or was previously moved out. Before every bootstrap edit, classify the candidate and record its canonical home:

- **`AGENTS.md` only:** an always-on session gate, cross-domain routing rule, or protection needed before a specific skill can be selected.
- **Owning skill:** domain execution, decision mechanics, or repeatable operational procedure.
- **Reference:** durable design, rationale, examples, or implementation detail needed only when that area is active.
- **Memory / dated record:** factual continuity, temporary context, or history—not policy.

The maintainer must answer: **Why would losing this before skill routing cause a material early-session failure?** If that answer is weak, the item is rejected from bootstrap and stored in its lower-layer canonical home. A moved item must not be copied back into bootstrap unless it independently passes this test.

### No-backflow review check
During every bootstrap audit, search the proposed/current bootstrap content for execution mechanics, domain-specific rules, repeated rationale, examples, catalogs, and historical detail. For each match, either name its lower-layer canonical home or keep it only with the explicit admission justification above. An edit is not complete while any such item is unresolved.

Bootstrap files should **not** become dumping grounds for:
- long mechanism tests
- repeated examples
- domain workflow detail that belongs in a skill
- operational history that belongs in dated memory or logs
- reference material that is only needed sometimes
- broad policy that is not specific to that bootstrap file's role
- giant per-item catalogs when grouped pointers would do
- one-off draft/special-case artifacts that belong in a lower-priority index

## Bootstrap-first classification model
Before editing anything, classify each candidate item of information:

### 1. Bootstrap rule
Keep in bootstrap only if missing it early would materially harm routing or safety.
Examples:
- top-level gating order
- mandatory skill-routing triggers
- concise behavioural constraints
- compact durable personal context

### 2. Skill logic
Move to the owning skill if it is domain-specific execution guidance.
Examples:
- invoice mirror rules
- expense capture mechanics
- CRM attribution mechanics
- calendar-send operational steps

### 3. Reference logic
Move to a reference file if it is durable but not needed every session.
Examples:
- long design notes
- implementation details
- recovery procedures
- fuller explanations and examples

### 4. Memory / dated memory
Move to memory if it is factual continuity rather than policy.
Examples:
- recent discoveries
- temporary priorities
- notable one-off lessons
- dated operating context

## File-role model
Use these defaults unless there is a strong reason not to:

- `AGENTS.md` = bootstrap gates, session rules, cross-domain routing order
- `HEARTBEAT.md` = heartbeat/watch-mode rules only
- `MEMORY.md` = curated long-term operating memory only
- `SYSTEM_MAP.md` = routing/discoverability map only
- `USER.md` = compact human facts/preferences only
- `SOUL.md` = voice/persona/core stance only
- `IDENTITY.md` = identity metadata only
- `TOOLS.md` = environment-specific notes only

If content does not match the file's role, move it.

## Concrete anti-drift lessons from recent audits
Use these as hard checks when auditing bootstrap files:
- `AGENTS.md` should not carry long execution mechanics if a compact bootstrap rule plus a reference/skill can preserve behavior.
- `SYSTEM_MAP.md` should be a true jumping-off map: thing, what it is, where to go. It should not become a giant reference-library catalog.
- `SYSTEM_MAP.md` should not duplicate the runtime-injected skill catalog. Do not store skill name/description/location lists or broad skill entry-point tables there; keep skill discoverability in runtime skill injection and keep `SYSTEM_MAP.md` focused on durable non-skill file/area routing.
- `HEARTBEAT.md` should contain watch-mode monitoring logic only. Broad communication policy, calendar-send policy, LinkedIn post policy, and other non-heartbeat rules do not belong there.
- When a section is mostly a long catalog, grouped pointers are usually better than listing every child document in bootstrap.
- When a section is mostly procedure/rationale, keep the trigger in bootstrap and move the mechanics out.

## Required workflow
1. **Protect first — exact copy, not merely a repository**
   - before rewriting, compressing, or materially restructuring an injected/bootstrap file, create a separately readable exact pre-edit copy with a dated, descriptive name
   - verify the copy is byte-for-byte equivalent to the live file before editing
   - a Git checkout, backup directory, or “the file is versioned” is not by itself proof that a recoverable pre-edit copy exists
   - if an exact copy cannot be created and verified, stop; do not rewrite the file

2. **Define the target role of the file**
   - say what this file is for in one sentence
   - say what explicitly does **not** belong in it

3. **Measure the current pressure**
   - identify the relevant budget/pressure signal first (for example `bootstrapMaxChars`, visible runtime truncation, or clearly oversized sections)
   - state which file(s) are the main pressure sources before editing
   - if the audit is about slimming, do not rely on vibes alone

4. **Audit the content by line of responsibility**
   For each bulky section, decide:
   - keep here
   - compress here
   - move to skill
   - move to reference
   - move to memory
   - delete as redundant

5. **Preserve behaviour while reducing size**
   Prefer:
   - shorter trigger wording
   - one rule instead of three restatements
   - pointer to the owning skill instead of embedded mechanics

6. **Check duplication**
   If the same logic appears in multiple bootstrap files, decide the canonical home and reduce the others to pointers or concise reminders.

7. **Review the exact diff before applying it**
   - compare the exact pre-edit copy with the proposed/current edit
   - account for every removed or condensed section as one of: retained here, moved to a named skill/reference, intentionally retired with reason, or unresolved
   - unresolved meaning loss is a hard stop; do not claim the edit is safe because the replacement is shorter
   - after editing, re-read the live file and verify the diff against the accounting list

8. **Update discoverability — mandatory, not optional**
   Every moved, split, renamed, or newly canonicalised item must have a verified route from the places future agents actually look:
   - identify the first lookup point (`SYSTEM_MAP.md`, a governing skill, or a reference index)
   - add or update the pointer at that lookup point
   - ensure the pointer names the canonical destination and its purpose
   - read the route and destination back after editing

   A file is not considered safely relocated merely because it exists somewhere. If the route is missing or ambiguous, stop and report the move as incomplete.

9. **Re-check after edits**
   - verify the file still performs its bootstrap role
   - confirm the moved logic has a clear canonical home
   - verify the discoverability route resolves from the expected first lookup point
   - state whether pressure was actually reduced, not just relocated noisily

10. **Report the effect**
   After edits, give a compact summary:
   - what stayed
   - what moved
   - what shrank
   - why function should be preserved or improved

## Compression rules
When slimming bootstrap files:
- keep triggers, remove essays
- keep constraints, remove repeated rationale
- keep one example only if the example is the cheapest way to prevent a real mistake
- prefer category-level phrasing over long enumerations when safe
- prefer grouped pointer sections over long per-file/per-doc catalogs
- remove policy clutter that belongs to a different bootstrap file or owning skill
- never remove a fail-closed trigger unless the same protection is moved to a clearly-owned canonical place
- when a section is detailed but still important, prefer a compact bootstrap trigger plus a nearby reference file over deleting the detail entirely

## Refinement retention vs bootstrap promotion
Not every useful refinement belongs in bootstrap.

Use this two-step model whenever a new lesson/refinement appears:

1. **Retention decision (always required)**
   - Decide where the refinement should live so it is not lost.
   - Valid homes include an owning skill, a reference/checklist file, or bootstrap if truly necessary.
   - The question here is: **"Where can this be stored durably?"**

2. **Bootstrap-promotion decision (strict threshold)**
   - Only promote the refinement into `AGENTS.md`/other bootstrap if missing it early would materially harm routing, safety, or cross-domain reply integrity before a more specific skill could help.
   - The question here is: **"Why must this be always loaded, rather than merely stored?"**

### Mandatory threshold test before adding a new bootstrap rule
Before adding a new line/bullet/rule to a bootstrap file, explicitly answer all three:
- **Why bootstrap?** What concrete early-session failure would happen if this lived only in the owning skill/reference?
- **Why not merge?** Can this be absorbed into an existing broader bootstrap rule instead of creating a new case-specific bullet?
- **Why this file?** Why does it belong in this bootstrap file rather than another governing skill/reference home?

If any answer is weak, do **not** add a new bootstrap rule yet.

### Preferred bias
- **Store refinements liberally** in the right lower layer.
- **Promote to bootstrap sparingly.**
- If a refinement is just an instance of an existing broader principle, strengthen or reuse the broader rule instead of adding a fresh special case.
- Near-pointer / live-context mistakes (for example: "this transcript", "that meeting", "the thing we were just talking about") should usually be handled by strengthening broader current-context-grounding rules rather than accumulating many object-specific bootstrap bullets.

## Fail-closed rules
- Do not compress a bootstrap file by silently deleting behaviour that has no new canonical home.
- Do not move domain rules out of bootstrap unless the owning skill/reference file is updated in the same workstream.
- Do not call a bootstrap cleanup complete if discoverability/routing is now worse.
- If uncertain whether something is bootstrap-critical, keep it temporarily and mark it for deliberate review rather than guessing.

## Typical triggers
Use this skill when Tom says things like:
- "slim down AGENTS.md"
- "audit the bootstrap files"
- "what should live in MEMORY vs AGENTS vs a skill?"
- "keep bootstrapping light"
- "these injected files are getting too big"
- "move the detail out but keep the quality"

## Outputs
This skill should usually update some combination of:
- the target bootstrap file(s)
- owning skills that absorb moved logic
- reference files for lower-priority detail
- `SYSTEM_MAP.md` for discoverability
- a short before/after explanation for Tom

## Success condition
The work is successful when:
- the bootstrap layer is smaller or cleaner
- routing/safety quality is preserved or improved
- each rule has a clearer canonical home
- future sessions are less likely to lose critical behaviour to truncation
- the audit names the specific pressure source(s) and shows whether the edit actually reduced bootstrap pressure rather than merely moving text around without effect

## Mandatory end-of-use review
After every real use of this skill, explicitly check with Tom whether:
- the file-role model still feels right
- anything remained in bootstrap that should move out
- anything moved out actually needed to stay
- the skill itself should be updated before the next bootstrap edit
