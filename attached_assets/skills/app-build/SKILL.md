---
name: app-build
description: Build a new app after planning/init are complete. Use when the app scope is agreed and implementation should proceed in a controlled, one-file-at-a-time way.
---

# App Build

## Goal

Implement the agreed build in a disciplined way, using the same checklist whether this is an internal Pi change, a new standalone app, or an external/client project.

## Process

1. Confirm the plan/acceptance criteria exist or were consciously kept lightweight for an internal patch.
2. Re-state the branch: internal Pi/self-build, new standalone app/system, or external/client/project.
3. Confirm the repo home / code home before making the change.
4. Build one coherent piece at a time; do not sprawl.
5. Keep changes understandable and testable.
6. Prefer explicitness over cleverness.
7. For every new external/client project, implement both paths consciously:
   - the **development/runtime path** (where the real code runs/builds/tests/deploys)
   - the **workspace control-plane path** (how the workspace GUI/control layer will later discover, launch, inspect, or open that project)
8. For GitHub-backed hosted-preview projects, keep the deployment chain explicit:
   - build on the Pi
   - commit/push to GitHub
   - hosted preview provider builds from GitHub
   - control plane retrieves the resulting public preview URL/status
9. Treat the **preview URL surfacing path** as part of the build, not a later polish item:
   - if a hosted preview/test environment exists, the build is not complete until there is a deterministic way for the control plane to retrieve the real public URL
10. Stop and surface uncertainty instead of silently improvising architecture.
11. Before calling implementation complete, state the git/update path: commit, push, and any deploy/restart requirement.
12. For external/client projects, also state whether the project has been wired into the workspace control plane yet, and if not, what is still missing (registry entry, runnable root, GitHub push route, preview URL discovery, auth/env, GUI action support).

## Rules

- Do not skip straight from idea to tangled implementation.
- Keep the build aligned with the planned workflow.
- Hand off to `app-test` before considering the work ready.
- For Pi/internal work, "done" does not just mean code changed locally; it means the repo/update path is handled or explicitly blocked.
- For external/client projects, "done" does not just mean the app runs locally; it must be clear whether the hosted preview/test environment is reachable and whether the workspace control plane can surface/control it.
- **Completion-status rule (MANDATORY):** before saying a build/change is complete, explicitly state:
  1. where the code lives,
  2. whether it was committed,
  3. whether it was pushed,
  4. whether deploy/restart/reload happened,
  5. what is blocked if any of those did not happen.
