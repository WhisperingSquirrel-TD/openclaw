---
name: app-build
description: Build a new app after planning/init are complete. Use when the app scope is agreed and implementation should proceed in a controlled, one-file-at-a-time way.
---

# App Build

## Goal

Implement the agreed app in a disciplined way.

## Process

1. Confirm the plan/acceptance criteria exist.
2. Build one coherent piece at a time; do not sprawl.
3. Keep changes understandable and testable.
4. Prefer explicitness over cleverness.
5. Stop and surface uncertainty instead of silently improvising architecture.

## Rules

- Do not skip straight from idea to tangled implementation.
- Keep the build aligned with the planned workflow.
- Hand off to `app-test` before considering the work ready.
