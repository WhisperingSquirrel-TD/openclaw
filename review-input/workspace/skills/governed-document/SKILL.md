---
name: governed-document
description: Create or update durable governed documents in the correct canonical location, preserving structure, lineage, references, and discoverability.
---

# Governed Document

_Last updated: 2026-06-15 14:41_

Use this when the job is not just "write a file", but "put this new file in the system properly".

This process exists to prevent:
- orphan files
- duplicate governance paths
- new files that are useful but structurally wrong
- forcing lightweight documents through heavyweight skill-packaging workflows

## Core principle
A new durable file must be placed by **lineage and trigger**, not by vibes.
If the file will later be used to govern app work, prefer putting stable intent, boundaries, and operator expectations into the canonical document rather than leaving them implicit in chat summaries.

Before creating it, decide:
1. what it is
2. why it exists
3. when it will be read
4. where it should live
5. how future sessions will discover it

## Classification check (MANDATORY)
Classify the new artifact first:
- **Policy** — why / commitment / governing intent
- **Process / Skill** — what happens, inputs → outputs, ordered workflow
- **Work Instruction** — exact task-level how-to for a narrower activity
- **Tool / Working file** — supporting means, tracker, scratchpad, log, template, queue, checklist

If you cannot classify it, do not create it yet.

## Decision route

### 1. Check whether a governing file already exists
Read the routing stack before creating anything:
- `ORGANIZATION.md` — policy / structure logic
- `SYSTEM_MAP.md` — routing and current homes
- relevant `skills/*/SKILL.md` if a domain workflow already governs the area

### 2. Decide whether this should be:
- a new standalone file
- a section added to an existing governing file
- a new skill/process
- a reference file under an existing area
- a transient working file rather than a persistent one

### 3. Apply the lightweight-vs-heavyweight rule
Use this process for:
- simple markdown/text documents
- new governed workspace files
- trackers, guides, maps, policies, references, instructions
- lightweight local skills that are primarily text/process and do not need scaffold tooling

Do **not** escalate to `skill-creator` unless the thing being created is truly a reusable skill package or the heavier scaffold is genuinely useful.

## Placement rules

### Policy
Usually lives at workspace root or another clearly-governing location and should be routed from `SYSTEM_MAP.md`.

### Process / Skill
Usually lives in `skills/<name>/SKILL.md` if it is a reusable workflow.

### Work Instruction
Usually lives either:
- inside the governing skill/file if narrow enough, or
- as a dedicated reference/work-instruction file if it would bloat the parent.

### Tool / Working file
Lives where the owning process would naturally look for it.
Examples:
- root working files for cross-system tools
- `reference/` for durable reference
- domain folders for domain-specific tools

## Discoverability rule (MANDATORY)
If future sessions will need to find the new file without luck:
1. update `SYSTEM_MAP.md`
2. add a clear routing line or table entry
3. do not bury the new file as an implicit assumption

## Lineage rule (MANDATORY)
For every new durable file, be able to answer in one line:
- **What policy justifies this file?**
- **What process/role uses it?**

If that answer is weak, the file is probably wrong or premature.

## Naming rule
Names should be literal, narrow, and purpose-revealing.
Avoid vague names unless the file is already a well-established canonical root file.

## Completion checklist
Do not call the work done until all are true:
- file created or updated
- classification decided
- placement justified
- `SYSTEM_MAP.md` updated if needed
- any relevant governing file updated if the structure/routing changed
- if the document governs app/system work, its success criteria, proof artifacts, and operator boundaries are explicit enough that later sessions can verify state from raw sources rather than inherited summaries

## Typical outputs
This process commonly updates one or more of:
- the new file itself
- `SYSTEM_MAP.md`
- `ORGANIZATION.md` if a new structural rule is needed
- the governing domain skill/file if the new file changes workflow expectations

## App/workspace handoff rule (MANDATORY)
If this process is used to create the canonical home for a new app, system, dashboard, control panel, or other software workspace:
1. use this skill first to place the artifact correctly and make it discoverable
2. then immediately route to `skills/app-plan/SKILL.md` before doing architecture, field design, page design, implementation planning, or build work
3. do not let governed-document placement substitute for app planning
4. **do not report the placement/design work as complete until the app-plan checklist has either been run or explicitly marked blocked**
5. if `app-plan` is not visible in the runtime skill catalog, check `skills/app-plan/SKILL.md` directly before declaring it unavailable

**Trigger:** the new durable file/workspace is primarily for a software product or interface rather than a static reference document.

**Mechanism:** before final response, ask: "Did this create or define a runnable app/system/workspace?" If yes, the completion checklist must include either `app-plan run` or `app-plan blocked: <reason>`. Missing that line means the governed-document workflow is incomplete.

## Example trigger patterns
- "write a new document for this"
- "create a file for this and make sure it sits properly in the system"
- "we need a better structure for this kind of doc"
- "where should this live?"
- "add the artefacts needed to keep this organised"

## Fail-closed rule
If the right home is unclear, say so and resolve the placement question before creating multiple overlapping files.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
