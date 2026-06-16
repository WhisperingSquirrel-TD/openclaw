---
name: app-plan
description: Plan a new app before any build work. Use when Tom wants a new app/project scoped, clarified, or broken into a concrete build/test/deploy path. Also use when spinning up a new external/client project so the project is linked into the workspace control plane from day one.
---

# App Plan

_Last updated: 2026-06-16 10:01_

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
6. What evidence would count as proof of completion for this specific request?
7. What repo/backup/update path should protect it afterwards?
8. What is the control-plane/GUI path from Tom's prompt to a usable preview/control surface?

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
- treat **workspace linkage** as mandatory setup: every new external/client project must be registered in the workspace control plane so it can later be tested/launched from the GUI without rediscovery
- define the control-plane metadata at planning time, even if runtime wiring happens later:
  - canonical project path on the Pi
  - repo/remote if any (required for deployable external/client projects; record the canonical GitHub URL)
  - build command
  - git push route
  - hosted preview provider (for example Vercel)
  - preview creation/discovery rule after GitHub push
  - whether it should appear in the dev-project runtime registry
  - what the GUI should eventually be able to do with it (open preview, run test, restart preview, view logs, stop preview, etc.)

## Process

1. Run the universal checklist spine.
2. Choose the correct branch (internal Pi/self-build, new standalone app/system, or external/client/project).
3. Clarify the goal, users, core workflow, and non-goals as needed for that branch.
4. Define the smallest useful version first.
5. Identify what must be proven in build vs what can wait.
6. For every brand-new external/client project, state the **workspace linkage plan** explicitly before build starts:
   - where the real code will live
   - what workspace registry/control entry will point to it
   - what commands the control plane should be allowed to run
   - how the public preview/test environment URL will be surfaced back to the GUI
7. State the architect/operator split explicitly:
   - Tom owns product intent, trade-offs, and approval of the target shape
   - L1 owns disciplined execution, file updates, verification, and surfacing ambiguity early
     Do not let L1 silently become the architect by making unapproved product or workflow decisions.
8. **Complex-system design/documentation rule (MANDATORY):** if the work is a multi-part system (for example CRM + queue + gateway + chat tool + send path), planning must define and point to one canonical design/operating document before implementation sprawls. That document must state:
   - the system goal and non-goals
   - the component boundaries/responsibilities
   - the user-facing acceptance criteria
   - the no-exec / control-plane expectation if relevant
   - the current phase/status
   - which docs must be kept in sync when the design changes
     If no such document exists yet, create or update it as part of planning rather than leaving the architecture implicit in chat.
9. Define the verification and observability spine before implementation starts:
   - what behavior will be proven by fast unit/repository tests
   - what behavior will be proven by integration tests
   - what end-to-end proof is actually needed
   - what logs/signals must exist to diagnose failure in production or on the Pi
10. Include an end-to-end sentence in the plan covering the full path:

- Tom prompts for a project
- project is created in the right code home
- runtime/preview environment can be started
- workspace control plane can discover/control it
- GUI can surface/open the real preview URL

11. Produce a concise implementation plan with clear phases.
12. Bound the automation up front: state which decisions/actions L1 may take without re-approval, which require Tom's confirmation, and what counts as a stop-and-ask condition.
13. Route implementation to the right next skill (`app-build`, `app-patch`, `app-test`, `app-deploy`) rather than building from vague intent.

## Additional mandatory rules for planning

- Use `reference/APP-ENGINEERING-TDD-LOGGING.md` when deciding how much TDD, integration coverage, and observability a system needs.
- For critical systems, do not leave test strategy or logging strategy implicit.
- Name the proof for both the happy path and at least the most important failure path.
- If the system has persistence, state transitions, APIs/gateway routes, or operational consequences when wrong, integration tests are mandatory by default.
- Planning is incomplete if it defines features but not how confidence and diagnosis will work.

## Notes

- These app skills are a **checklist framework**, not a claim that every task is a brand new app.
- Do not start coding from an unclear idea.
- Prefer a smaller first version with explicit acceptance criteria and named proof artifacts.
- Separate raw source from interpreted state: when stating status, route, repo, preview URL, task state, or deployment expectation, identify the primary source that will later be checked rather than relying on memory summaries.
- Keep the plan lightweight and practical.
- For Pi/internal work, lightweight planning is fine — but never skip repo-home and post-build update thinking.
