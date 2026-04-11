---
name: app-plan
description: Plan a new app or product. Extracts goal, users, MVP scope, pages, flows, data model, auth, integrations, and build phases. Outputs a spec file to specs/<project-name>.md. Use when Tom says "plan a project", "create a spec for X", or "I want to build X". Stops after writing the spec — does not create repos or write code.
---

# app-plan

**Purpose:** Write a complete project spec before any code is touched. This skill covers planning only — it does not create repos, write code, or trigger any build action.

---

## Trigger

Use this skill when Tom says any of:
- "Plan a new project called X"
- "Create a spec for X"
- "I want to build X"
- "Plan the MVP for X"

---

## Required inputs

Before starting, confirm you have:
1. **Project name** — used as `specs/<project-name>.md`
2. **Goal** — what the product does and for whom
3. **Rough scope** — features Tom has in mind

If any are missing, ask for them before proceeding. Do not guess.

---

## Process

Work through the following sections in order. Ask clarifying questions per section if needed. Do not move to the next section until the current one is clear.

### 1. Goal
- What does this product do?
- Who is the primary user?
- What problem does it solve?

### 2. MVP scope
- What is the smallest version that delivers value?
- What is explicitly NOT in scope for MVP?

### 3. Pages and flows
- List every page or screen in the MVP
- Describe the key user flows (entry → action → outcome)

### 4. Data model
- What entities exist? (users, projects, records, etc.)
- What are the key relationships?
- What persists vs what is ephemeral?

### 5. Auth
- Is authentication needed?
- What method? (none / email+password / magic link / OAuth / Supabase auth)

### 6. Integrations
- Any third-party services? (email, SMS, payments, external APIs)
- Any internal OpenClaw integrations?

### 7. Build phases
Break the work into sequential phases that can each be built independently. Each phase should be independently deployable and reviewable.

Format:
```
Phase 1 — <name>: <1-line description>
Phase 2 — <name>: <1-line description>
...
```

### 8. Testing plan
- What should be lint/typecheck/build checked on every phase?
- Any specific flows to verify manually after each build?
- Any optional smoke/e2e tests?

---

## Output

Write the completed spec to:
```
~/.openclaw/workspace/specs/<project-name>.md
```

Format:
```markdown
# <Project Name> — Spec

## Goal
...

## MVP scope
...

## Out of scope (MVP)
...

## Pages and flows
...

## Data model
...

## Auth
...

## Integrations
...

## Build phases
Phase 1 — ...
Phase 2 — ...

## Testing plan
...

## Status
Spec written: <date>
Approved: [ pending Tom approval ]
```

---

## Stop condition

**Stop immediately after writing the spec file.**

Do not:
- Create a repo
- Write any code
- Trigger app-init
- Suggest next steps beyond "spec is ready for your review"

Report to Tom:
```
Spec written to ~/.openclaw/workspace/specs/<project-name>.md

Ready for your review. Reply "approved" to move to init, or send changes.
```

---

## Failure modes

| Situation | Action |
|-----------|--------|
| Project name not given | Ask before starting |
| Goal is ambiguous | Ask before writing |
| Specs directory missing | Create it: `mkdir -p ~/.openclaw/workspace/specs/` |
| Cannot write file | Stop and report the error clearly |

**Never guess at scope. Never start building. Never proceed without Tom's review.**
