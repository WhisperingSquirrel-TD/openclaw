---
name: app-deploy
description: Deploy a tested app after Tom approves. Use when build and test are done, preview is ready, and deployment/merge needs to happen under explicit sign-off.
---

# App Deploy

_Last updated: 2026-06-15 14:41_

## Goal

Move a tested build to the approved destination without skipping sign-off, while distinguishing between internal Pi changes and external/client deployments.

## Process

1. Confirm build/test passed.
2. Confirm which branch of work this is: internal Pi/self-build, new standalone app/system, or external/client/project.
3. Confirm Tom explicitly approved deployment when a real deploy/restart/merge is involved.
4. Name the deployment proof target before acting: what exact artifact or observed state will prove this deploy completed successfully.
5. Follow the project’s deployment route.
6. For GitHub-backed hosted-preview projects, report the full chain explicitly:
   - what was built on the Pi
   - what commit/branch was pushed to GitHub
   - which hosted preview provider picked it up
   - what preview URL or deploy status resulted
7. Report outcome clearly, including commit/push/deploy state.

## Rules

- No deploy without explicit Tom approval.
- No merge/deploy just because the app looks ready.
- Separate raw source from interpreted state: deploy status must come from the live deploy/provider/runtime evidence, not from the expectation that a push "should have" worked.
- Separate preview/review from production deployment.
- Internal Pi work may only need restart/reload rather than a separate public deployment, but the outcome still needs to state whether GitHub/repo state was updated.
- For deployable external/client projects, GitHub repo linkage is not optional context: the deploy report must name the canonical repo URL/remote and whether the hosted preview is building from that repo as intended.
- Bounded automation still applies at deploy time: if the needed action would change destination, visibility, or operator workflow beyond the approved route, stop and ask rather than improvising.
