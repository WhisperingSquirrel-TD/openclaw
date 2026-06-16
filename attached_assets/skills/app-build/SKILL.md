---
name: app-build
description: Build a new app after planning/init are complete. Use when the app scope is agreed and implementation should proceed in a controlled, one-file-at-a-time way.
---

# App Build

_Last updated: 2026-06-15 14:41_

## Goal

Implement the agreed build in a disciplined way, using the same checklist whether this is an internal Pi change, a new standalone app, or an external/client project.

## Process

1. Confirm the plan/acceptance criteria exist or were consciously kept lightweight for an internal patch.
2. Confirm the named proof of completion for this slice exists: what artifact, check, state transition, or observable behavior will prove this build step is actually done.
3. Re-state the branch: internal Pi/self-build, new standalone app/system, or external/client/project.
4. Confirm the repo home / code home before making the change.
5. State the architect/operator split for the current slice if it matters:
   - Tom owns product intent, trade-offs, and approval of non-obvious shape changes
   - L1 owns disciplined execution, source-of-truth checks, and surfacing uncertainty early
6. Build one coherent piece at a time; do not sprawl.
7. Keep changes understandable and testable.
8. Prefer explicitness over cleverness.
9. For every new external/client project, implement both paths consciously:
   - the **development/runtime path** (where the real code runs/builds/tests/deploys)
   - the **workspace control-plane path** (how the workspace GUI/control layer will later discover, launch, inspect, or open that project)
10. For GitHub-backed hosted-preview projects, keep the deployment chain explicit:

- build on the Pi
- commit/push to GitHub
- hosted preview provider builds from GitHub
- control plane retrieves the resulting public preview URL/status

11. Treat the **preview URL surfacing path** as part of the build, not a later polish item:

- if a hosted preview/test environment exists, the build is not complete until there is a deterministic way for the control plane to retrieve the real public URL

12. Stop and surface uncertainty instead of silently improvising architecture.
13. Before calling implementation complete, state the git/update path: commit, push, and any deploy/restart requirement.
14. For external/client projects, also state whether the project has been wired into the workspace control plane yet, and if not, what is still missing (registry entry, runnable root, GitHub push route, preview URL discovery, auth/env, GUI action support).
15. **Chat-usable completion rule (MANDATORY):** if Tom asks to build something so it can be run/used "from chat", do not stop at a backend bridge or control-plane route alone. Completion requires one of:

- an existing first-class tool in the current runtime can actually call the new path end-to-end, or
- the build explicitly includes the chat/runtime wiring layer that makes it callable from this session class, or
- you clearly say the work is only the backend foundation and that it is **not yet usable from chat** before implying success.

16. **Outcome-over-layer rule:** when Tom's request is phrased as an outcome (e.g. "so you can run it from chat"), treat that outcome as the acceptance criterion. Do not present a lower layer (API, gateway route, config, internal bridge) as the solved thing unless that lower layer actually delivers the requested user-facing capability.
17. **Discriminating-debug rule (MANDATORY):** when an integration still fails after one plausible fix, stop proposing adjacent guesses and isolate the failing layer with the smallest direct test. For a chat/runtime tool path, the required chain is: (a) plugin discovered, (b) tool exposed in live agent tool catalog, (c) tool invocation succeeds, (d) downstream service responds, (e) requested end-to-end action succeeds. After each step, state exactly which layer is now proven and which remains unproven.
18. **No-premature-success rule (MANDATORY):** do not say "usable", "working", "fixed", or equivalent until the exact requested workflow has completed successfully at least once. For this class of task, that means the real requested action must run end-to-end; partial progress (tool visible, API reachable, job submitted, etc.) must be described only as partial progress.
19. **No-gated-shortcut-while-building-ungated-path rule (MANDATORY):** if Tom asks to build a route that avoids a gate/tool/dependency (for example "without exec"), do not use the gated route to complete the user-facing task unless Tom explicitly approves that as a temporary workaround. A gated workaround may be used only for tightly scoped diagnostics to isolate a failing layer, and it must be labelled as temporary containment, not completion.
20. **Goal-protection rule (MANDATORY):** when debugging a system whose purpose is to remove friction, do not defeat the purpose by bypassing the target path just to get the immediate outcome. Protect the build goal first; if a workaround undermines the architecture Tom asked for, stop and ask before using it.
21. **Complex-system documentation sync rule (MANDATORY):** when building a system with multiple layers (for example CRM selection, generation queue, gateway, chat tool, review/send path), do not let the architecture live only in code and chat. Update the canonical design/operating document as the build evolves so it stays truthful about:

- what the system is
- how it is meant to be operated
- which layers are live vs partial
- what first-class no-exec path exists
- what still depends on restart/reload/manual steps
  If the implementation changes the operator route or architecture, the documentation update is part of the build, not optional polish.

## Rules

- Do not skip straight from idea to tangled implementation.
- Keep the build aligned with the planned workflow.
- Separate raw source from interpreted state: use live repo status, build output, deployment records, and runtime evidence when reporting state; do not promote recollection or prior summaries into current fact.
- Bound automation: keep moving inside the approved slice, but stop and ask before changing architecture, widening scope, inventing operator workflow, or spending approval on a different problem than Tom asked to solve.
- Hand off to `app-test` before considering the work ready.
- For Pi/internal work, "done" does not just mean code changed locally; it means the repo/update path is handled or explicitly blocked.
- For external/client projects, "done" does not just mean the app runs locally; it must be clear whether the hosted preview/test environment is reachable and whether the workspace control plane can surface/control it.
- **Completion-status rule (MANDATORY):** before saying a build/change is complete, explicitly state:
  1. where the code lives,
  2. whether it was committed,
  3. whether it was pushed,
  4. whether deploy/restart/reload happened,
  5. what is blocked if any of those did not happen.
