---
name: weekly-review
description: Run Tom's Friday weekly system review. Use for end-of-week reflection on how to improve the system, including BACKLOG.md, TASKS.md, SOUL_PENDING.md, relevant memory/lessons, and any system/process changes that should be baked in.
---

# Weekly Review

Use this on the Friday review / reflection cycle.

## Purpose
Review the week as a whole and identify concrete improvements to the system.
This is broader than a pure self-reflection: it should cover backlog, task/admin friction, process changes, structural issues, and SOUL-level proposals.

## Read
1. `SYSTEM_MAP.md`
2. `BACKLOG.md`
3. `TASKS.md`
4. `L1-IMPROVEMENTS.md`
5. `SOUL_PENDING.md`
6. `memory/lessons.md` (historical context only if useful)
7. daily memory files for the last 7 days
8. any obviously relevant files surfaced by the above (skills, reference files, audit files)

## Review lenses
### 1. System improvements
- What should be improved, built, simplified, split, merged, or retired?
- What should be baked into the system more explicitly?

### 2. Backlog and task hygiene
- What in `BACKLOG.md` still matters?
- What in `TASKS.md` is stale, drifting, misfiled, or should move elsewhere?
- What in `L1-IMPROVEMENTS.md` should be promoted, merged, clarified, or retired?
- Are there improvements sitting in chat/memory that should be promoted into backlog or skills?

### 3. Learning / process quality
- What did we learn this week?
- Were the right files/skills updated?
- Does `SYSTEM_MAP.md` still reflect the current structure?
- Are there repeated misses that need stronger process changes?

### 4. SOUL / policy proposals
- Is there anything that should be proposed in `SOUL_PENDING.md` for Tom's review?
- Only stage SOUL-level changes when they truly belong at policy/runtime level.

## Actions
- Patch relevant skill/process/reference files where the improvement is clear
- Update `SYSTEM_MAP.md` if routing/structure changed
- Add or clean up `BACKLOG.md` / `TASKS.md` items where needed
- Add SOUL-level proposals to `SOUL_PENDING.md` only when appropriate

## Output to Tom
Send a concise Friday review with sections:
- **System** — important improvements made / needed
- **Backlog** — notable items to discuss, add, remove, or prioritise
- **Process / learning** — what was tightened this week
- **Needs your review** — anything in `SOUL_PENDING.md` or other decisions Tom should make

## Rules
- Prefer concrete changes over commentary
- Do not just summarise the week; improve the system
- Use `SYSTEM_MAP.md` as the routing/checkpoint file throughout

## Model routing pattern (MANDATORY)
Use the `local-llm` route for first-pass pattern spotting, clustering, rough synthesis of recurring issues, or internal draft structuring **only when** the work can be kept to one small working slice at a time.
Small slice = one file, one dated chunk, or one clean subsection that can stand alone.
Use the stronger cloud route for final recommendations, policy/process changes, and anything structurally important.
Do not use the local route for broad cross-week judgement, messy chunking, or when the Pi is busy enough that CPU/RAM contention would be unwise.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
