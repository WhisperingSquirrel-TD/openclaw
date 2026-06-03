---
name: app-plan
description: Plan a new app before any build work. Use when Tom wants a new app/project scoped, clarified, or broken into a concrete build/test/deploy path.
---

# App Plan

Use this skill at the start of any new app request.

## Goal

Use the standard development checklist to decide what kind of build this is, then only apply the planning parts that actually fit.

## Universal checklist spine (MANDATORY)

Run these questions for **all** development requests, even if some steps later become N/A:

1. What is being built or changed?
2. Who is it for? (Tom/internal, Tom's own business system, or external/client/project)
3. Where should the runnable code live?
4. Is this a brand new app/system, or a patch to an existing one?
5. What acceptance criteria prove it works?
6. What repo/backup/update path should protect it afterwards?

## Branching logic

### Branch A — Internal Pi/self-build work

Use when Tom wants something built for his own Pi/OpenClaw/business operating stack.

- still run the checklist spine
- do **not** assume a new standalone workspace/repo is needed
- prefer existing Pi/runtime repo homes first
- planning can be lighter, but repo home + acceptance criteria + post-build git path must still be stated

### Branch B — New standalone app/system/workspace

Use when the work really is a new software product/interface/workspace.

- define the app shape properly
- define whether it needs its own workspace and/or repo
- route to fuller app build workflow after scope is clear

### Branch C — External/client/project build

Use when the build is for another person, client, or project context.

- capture client/project context
- be clearer about boundaries, deliverables, and deployment target
- keep stronger separation between preview/review and deployment

## Process

1. Run the universal checklist spine.
2. Choose the correct branch (internal Pi/self-build, new standalone app/system, or external/client/project).
3. Clarify the goal, users, core workflow, and non-goals as needed for that branch.
4. Define the smallest useful version first.
5. Identify what must be proven in build vs what can wait.
6. Produce a concise implementation plan with clear phases.
7. Route implementation to the right next skill (`app-build`, `app-patch`, `app-test`, `app-deploy`) rather than building from vague intent.

## Notes

- These app skills are a **checklist framework**, not a claim that every task is a brand new app.
- Do not start coding from an unclear idea.
- Prefer a smaller first version with explicit acceptance criteria.
- Keep the plan lightweight and practical.
- For Pi/internal work, lightweight planning is fine — but never skip repo-home and post-build update thinking.
