---
name: app-test
description: Test a built app before preview/deploy. Use when implementation exists and needs structured verification against the agreed acceptance criteria.
---

# App Test

## Goal

Verify that the built change works before Tom sees it as ready.

## Process

1. Check the build/patch against the planned acceptance criteria.
2. Run the relevant self-test workflow for the project or Pi/internal change.
3. Record pass/fail clearly.
4. Record what was tested, what was not tested, and what still depends on live deployment/runtime verification.
5. For external/client projects, test both layers explicitly where relevant:
   - project/runtime layer: build/test/deploy/preview service itself
   - workspace control-plane layer: registry/path/env/URL discovery/GUI panel actions if applicable
6. **Classify the failing layer before proposing the next action**:
   - project/runtime/app code failure
   - hosted preview provider/deployment failure
   - control-plane/backend failure
   - GUI/frontend failure
     Do not widen the fix to another layer unless there is evidence that layer is also broken.
7. Add an end-to-end verdict whenever relevant:
   - can Tom go from asking for the project to actually opening/controlling the preview through the GUI/control plane?
8. If the test fails, route back to build rather than passing failure forward.

## Rules

- Do not call something ready because it mostly works.
- Testing is part of the build workflow, not an optional extra.
- Be explicit about what was tested and what was not.
- For Pi/internal work, include whether the git/update path is ready for push or still blocked.
- For external/client projects with hosted preview environments, distinguish clearly between:
  - local build/test pass
  - GitHub push/update path healthy
  - hosted preview reachable from the GitHub-backed provider
  - workspace GUI/control-plane able to surface the real public URL and actions
  - Tom actually having a usable end-to-end path from request → project → preview/control surface
