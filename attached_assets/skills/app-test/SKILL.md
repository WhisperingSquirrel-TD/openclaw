---
name: app-test
description: Test a built app before preview/deploy. Use when implementation exists and needs structured verification against the agreed acceptance criteria.
---

# App Test

## Goal

Verify that the built app works before Tom sees it as ready.

## Process

1. Check the app against the planned acceptance criteria.
2. Run the relevant self-test workflow for the project.
3. Record pass/fail clearly.
4. If the test fails, route back to build rather than passing failure forward.

## Rules

- Do not call something ready because it mostly works.
- Testing is part of the build workflow, not an optional extra.
- Be explicit about what was tested and what was not.
