---
name: app-deploy
description: Deploy a tested app after Tom approves. Use when build and test are done, preview is ready, and deployment/merge needs to happen under explicit sign-off.
---

# App Deploy

## Goal

Move a tested build to the approved destination without skipping sign-off, while distinguishing between internal Pi changes and external/client deployments.

## Process

1. Confirm build/test passed.
2. Confirm which branch of work this is: internal Pi/self-build, new standalone app/system, or external/client/project.
3. Confirm Tom explicitly approved deployment when a real deploy/restart/merge is involved.
4. Follow the project’s deployment route.
5. Report outcome clearly, including commit/push/deploy state.

## Rules

- No deploy without explicit Tom approval.
- No merge/deploy just because the app looks ready.
- Separate preview/review from production deployment.
- Internal Pi work may only need restart/reload rather than a separate public deployment, but the outcome still needs to state whether GitHub/repo state was updated.
