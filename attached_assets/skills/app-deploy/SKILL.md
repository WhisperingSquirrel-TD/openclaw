---
name: app-deploy
description: Deploy an app to production on Vercel — but only after explicit Tom approval, passing checks, and a reviewed preview. Hard-gated: requires approval, passing tests, existing preview, and Tom's QA sign-off. Use when Tom says "deploy X", "deploy to production", "ship it", or "push to production". Never triggered automatically by other skills.
---

# app-deploy

**Purpose:** Deploy to production on Vercel — but only after explicit Tom approval, passing checks, and a reviewed preview. This skill never deploys speculatively.

---

## Trigger

Use this skill when Tom says any of:
- "Deploy X"
- "Deploy to production"
- "Ship it"
- "Push to production"

**This skill must never be triggered automatically by app-build or app-test.**

---

## Hard requirements — all must be met before deploying

1. **Tom has explicitly approved** — a clear message like "deploy it", "ship it", "go live", "approve"
2. **All self-tests passing** — lint, typecheck, build, tests (app-test ran and passed)
3. **Preview URL exists** — Vercel preview was generated after the last push
4. **Tom has reviewed the preview** — Tom acknowledged reviewing it (even briefly)
5. **Production target defined** — the Vercel project is linked and VERCEL_TOKEN is set

If any requirement is not met: **stop and state exactly which requirement is missing. Do not deploy.**

---

## Pre-deploy checklist

Run through this checklist before touching deploy:

```
[ ] Tom said: approve / deploy / ship (exact phrase noted)
[ ] Last app-test result: all passed
[ ] Preview URL confirmed: <url>
[ ] Tom reviewed preview: yes
[ ] VERCEL_TOKEN in .env: yes
[ ] Vercel project linked: yes
[ ] Production domain configured or default vercel.app OK: confirmed
```

If any box cannot be ticked: stop and report which one.

---

## Process

### Step 1 — Final verification

```bash
cd ~/.openclaw/workspace/projects/<project-name>
git log --oneline -1   # confirm which commit is being deployed
npm run build           # final build check before promote
```

If build fails: **stop. Do not deploy. Report to Tom.**

### Step 2 — Promote preview to production

```bash
npx vercel --prod --token $VERCEL_TOKEN
```

This promotes the current build to production.

### Step 3 — Verify production URL

```bash
npx vercel ls --token $VERCEL_TOKEN
```

Confirm the production URL is live and matches the expected domain.

### Step 4 — Record rollback path

Note the previous deployment ID for rollback:
```bash
npx vercel ls --token $VERCEL_TOKEN | head -10
```

---

## Output

```
Deployed to production — <project-name>

Production URL: <url>
Commit: <git hash> — <commit message>
Deployed at: <timestamp>

Rollback: If needed, run:
  npx vercel rollback --token $VERCEL_TOKEN

Next steps:
- Verify on your phone
- If anything is wrong, say "rollback X" and I'll revert immediately
```

---

## Stop conditions

Stop immediately and report if:
- Tom's approval is absent or ambiguous
- app-test has not run since the last code change
- Preview URL is missing
- VERCEL_TOKEN is missing
- Final build check fails
- Vercel deploy command fails

---

## Failure modes

| Situation | Action |
|-----------|--------|
| No explicit approval | Stop — "I need an explicit go-ahead before deploying. Say 'deploy it' or 'ship it' to confirm." |
| Tests not run | Stop — "Self-tests have not been run since the last change. Run app-test first." |
| No preview reviewed | Stop — "Preview hasn't been reviewed yet. Check <url> and confirm before I deploy." |
| VERCEL_TOKEN missing | Stop — "VERCEL_TOKEN not found in .env. Add it and retry." |
| Vercel project not linked | Stop — "Vercel project not linked. Run app-init or link manually with: npx vercel link" |
| Build fails on final check | Stop — "Final build check failed. Fix before deploying." |
| Deploy command fails | Stop — report exact Vercel error. Do not retry automatically. |
| Production URL not resolving | Report — "Deploy command succeeded but URL may take a moment to propagate." |

**No speculative deploys. No "it should be fine." Explicit approval, every time.**
