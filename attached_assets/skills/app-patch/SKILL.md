---
name: app-patch
description: Patch an existing app safely. Use when Tom wants a specific change to an existing project and the repo should not be reinitialised from scratch.
---

# App Patch

## Goal

Make a controlled change to an existing app.

## Process

1. Confirm the exact requested change in plain English.
2. Treat it as a patch, not a rebuild.
3. Keep the scope tight.
4. Test before asking for deploy approval.

## Rules

- Do not reinitialise an existing project as if it were new.
- Do not widen the patch beyond the agreed change.
- Route deploy/merge through explicit approval.
