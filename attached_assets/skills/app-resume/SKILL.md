---
name: app-resume
description: Re-orient on an existing project at the start of a new conversation. Reads the spec, PROGRESS.md session journal, and recent git history to rebuild context before any work begins. Use when Tom says "resume X", "pick up X", "continue X", "where were we on X", or "catch me up on X".
---

# app-resume

**Purpose:** Rebuild full context on an existing project at the start of a new session, so work can continue without repeating decisions or losing track of what was done. This skill runs first, before any code is written or commands are run.

---

## Trigger

Use this skill when Tom says any of:
- "Resume \<project\>"
- "Pick up \<project\>"
- "Continue \<project\>"
- "Where were we on \<project\>?"
- "Catch me up on \<project\>"
- "Let's work on \<project\>"

---

## Process

Run all reads first. Do not ask questions or start work until you have read everything.

### Step 1 — Read the spec

```bash
cat ~/.openclaw/workspace/specs/<project-name>.md
```

Note:
- Total number of phases
- Which phases are marked complete in the spec
- The current phase's acceptance criteria

---

### Step 2 — Read the session journal

```bash
cat ~/.openclaw/workspace/projects/<project-name>/PROGRESS.md 2>/dev/null \
  || echo "(No PROGRESS.md found — project may pre-date this convention)"
```

Note:
- Last session date and what was completed
- Any open decisions or unresolved issues
- Any known test failures or limitations
- What the next step was at the end of the last session

---

### Step 3 — Read recent git history

```bash
cd ~/.openclaw/workspace/projects/<project-name>
git log --oneline -10
git status
```

Note:
- Last commit message and date
- Whether the working tree is clean
- Whether there are uncommitted changes

---

### Step 4 — Summarise to Tom

After reading everything, give Tom a short status summary in this format:

```
Picked up: <project-name>

Last session (<date from PROGRESS.md>):
  <2–3 sentence summary of what was done>

Current state:
  Phase:     <N of M>
  Last commit: <hash and message>
  Working tree: clean / <N files changed>

Open items from last session:
  - <issue or decision left unresolved>
  - <known limitation>

Next step: <exactly what was planned at end of last session>

Ready. Tell me to continue, or give me new instructions.
```

If PROGRESS.md does not exist, say so clearly and reconstruct what you can from git history and the spec.

---

## After the summary

Wait for Tom's instruction before doing anything. Do not start building, fixing, or planning without being asked.

---

## Stop conditions

- If the spec does not exist: "No spec found for \<project\>. Has it been planned yet?"
- If the project directory does not exist: "Project directory not found. Has it been initialised?"

---

## Notes

- PROGRESS.md is written by L1 at the end of every app-build session. If it is missing, the project pre-dates this convention or the last session ended without writing it.
- Never skip this skill and jump straight into code. Context gaps cause regressions and repeated decisions.
