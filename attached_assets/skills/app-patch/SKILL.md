---
name: app-patch
description: Patch an existing app safely. Use when Tom wants a specific change to an existing project and the repo should not be reinitialised from scratch.
---

# App Patch

## Goal

Make a controlled change to an existing system without confusing "patch" with "new app", while still using the same development checklist spine.

## Process

1. Confirm the exact requested change in plain English.
2. Confirm what system/repo this patch belongs to.
3. Re-state the branch: internal Pi/self-build, Tom-owned system, or external/client/project.
4. Treat it as a patch, not a rebuild.
5. Keep the scope tight.
6. Test before asking for deploy approval.
7. Before calling the patch complete, handle the repo/update path: commit, push, and any deploy/restart step — or explicitly say what is still blocked.

## Rules

- Do not reinitialise an existing project as if it were new.
- Do not widen the patch beyond the agreed change.
- Route deploy/merge through explicit approval where appropriate.
- Internal Pi patches still go through the checklist; they just skip the irrelevant new-app/repo-creation parts.
- **Completion-status rule (MANDATORY):** before saying a patch is complete, explicitly state:
  1. where the code lives,
  2. whether it was committed,
  3. whether it was pushed,
  4. whether deploy/restart/reload happened,
  5. what is blocked if any of those did not happen.
