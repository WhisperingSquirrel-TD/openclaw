---
name: app-test
description: Run the full self-test suite (lint, typecheck, build, test) before handing off to Tom. Blocks handoff if any check fails — never grants a partial pass or bluffs a result. Use when Tom says "run tests on X", "test phase N", "check X before review", or "self-test X". Can also be called internally by app-build before a push.
---

# app-test

**Purpose:** Run the full self-test suite before any handoff to Tom. Checks must all pass before a preview is considered ready. This skill blocks handoff — it does not grant a partial pass.

---

## Trigger

Use this skill when Tom says any of:
- "Run tests on X"
- "Test phase N"
- "Check X before review"
- "Self-test X"

Or call this skill internally from app-build before the push step.

---

## Required inputs

1. **Project name** — must have an initialised repo
2. Repo at `~/.openclaw/workspace/projects/<project-name>/`

---

## Test sequence

Run each step in order. **Stop on the first failure and report it. Do not continue to later steps.**

### Step 1 — Lint

```bash
cd ~/.openclaw/workspace/projects/<project-name>
npm run lint
```

Expected: zero errors, zero warnings (or only pre-approved warnings).

### Step 2 — Typecheck

```bash
npm run typecheck
```

Expected: zero TypeScript errors.

### Step 3 — Build

```bash
npm run build
```

Expected: build completes without error. A warning is acceptable only if it was pre-existing before this phase.

### Step 4 — Unit/integration tests

```bash
npm test
```

Expected: all tests pass. No skipped tests that were previously passing.

### Step 5 — Optional smoke/e2e (if configured)

```bash
npm run test:e2e 2>/dev/null || echo "No e2e configured — skipping"
```

Only run if e2e is configured in the project. Never fail the suite on a missing e2e setup.

---

## Superpowers test discipline

These rules apply during testing:

### No bluffing
- Never report a test as passing if it is not
- Never omit a failing step from the report
- Never suppress output to hide errors

### No skipping
- Do not skip lint because "it's just style"
- Do not skip typecheck because "it mostly works"
- Do not skip build because "it built last time"

### Fix first, report second
- If a failure is trivially fixable (missing semicolon, unused import), fix it and re-run
- If a failure requires architectural change or scope decision, stop and report to Tom
- Never push a fix you are not confident in just to make the test pass

### Clear separation
- A test run is either: **all pass** or **failed at step N**
- There is no "mostly passing" state

---

## Output

### All passing

```
Self-test complete — <project-name>

✓ Lint       — passed
✓ Typecheck  — passed
✓ Build      — passed
✓ Tests      — passed (N tests)
✓ E2e        — passed / not configured (skipped)

All checks passed. Ready for handoff.
```

### Failure

```
Self-test FAILED — <project-name>

✓ Lint       — passed
✓ Typecheck  — passed
✗ Build      — FAILED

Error output:
<exact error from npm run build>

Stopping here. Not pushing. Fix required before handoff.
```

---

## Stop conditions

Stop and report if:
- Any test step exits with a non-zero code
- Build produces errors (not just warnings)
- Tests report failures or errors

**Do not push. Do not report to Tom as ready. Fix or escalate.**

---

## Failure modes

| Situation | Action |
|-----------|--------|
| npm not found | Stop — "npm not available in project directory. Check repo setup." |
| Script not defined in package.json | Stop — "Script 'X' not defined in package.json. Add it or skip explicitly." |
| Lint errors | Fix trivial ones; stop and report non-trivial ones |
| Type errors | Stop — report exact error and file location |
| Build errors | Stop — report exact error |
| Test failures | Stop — report which tests failed and why |
| Flaky test | Report as flaky, do not mark as passing |
