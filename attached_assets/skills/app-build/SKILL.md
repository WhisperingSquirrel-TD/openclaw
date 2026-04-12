---
name: app-build
description: Implement one approved build phase of an app project. Reads the spec, builds only the agreed scope for that phase, pushes to GitHub, generates a Vercel preview, and returns a standard preview handoff report. Use when Tom says "build phase N", "build phase N of X", or "implement phase N". Enforces Superpowers coding discipline — no speculation, no scope creep.
---

# app-build

**Purpose:** Implement one approved build phase. Read the spec, build only the agreed scope, push to GitHub, generate a Vercel preview, and return the standard preview handoff report. One phase at a time.

---

## Trigger

Use this skill when Tom says any of:
- "Build phase N"
- "Build phase N of X"
- "Implement phase N"
- "Continue building X"

---

## Required inputs

Before starting, confirm you have:
1. **Project name** — must have an approved spec and initialised repo
2. **Phase number** — which phase from the spec to implement
3. Spec file at `~/.openclaw/workspace/specs/<project-name>.md`
4. Repo at `~/.openclaw/workspace/projects/<project-name>/`

If any are missing, stop and ask. Do not guess.

---

## Coding discipline (Superpowers patterns)

These rules govern how code is written in this skill. They are not optional.

### Work in verified steps
- Make one logical change at a time
- Verify it compiles/runs before moving to the next
- Never chain multiple unverified changes

### Strict scope
- Implement only what the current phase defines in the spec
- If you find something missing from the spec, note it for the next phase — do not build it now
- No "while I'm here" additions

### No speculation
- Do not add features, pages, or components not in the spec
- Do not add abstractions for "future flexibility" unless the spec requires them
- Do not change styling, naming, or architecture outside the phase scope

### Review before push
- Re-read every changed file before committing
- Check: does this implement only what was agreed? Is anything missing? Is anything extra?

### Small commits
- Commit logically related changes together
- Write clear commit messages: `feat: add <what> for phase N`

---

## Process

### Step 1 — Read the spec

```bash
cat ~/.openclaw/workspace/specs/<project-name>.md
```

Identify exactly what Phase N specifies. Note the acceptance criteria.

### Step 2 — Check current state

```bash
cd ~/.openclaw/workspace/projects/<project-name>
git status
git log --oneline -5
```

Ensure you are on the correct branch and the working tree is clean.

### Step 3 — Implement

Work through the phase requirements in order. Apply Superpowers discipline throughout:
- One change, verify, next change
- No scope creep
- No speculation

### Step 4 — Commit and push

```bash
git add .
git commit -m "feat: phase N — <short description>"
git push origin main
```

If push fails: **stop and report the exact error.**

### Step 5 — Hand off to mgmt-bot for testing and preview

You cannot run shell commands directly. After pushing, tell Tom:

> "Code is pushed. To test and get a preview URL, send this to your management bot on Telegram:
> `/dev-test <project-name>`
> If all checks pass, it will prompt you to run:
> `/dev-run <project-name>`
> That will install dependencies, build, and generate a Vercel preview link for you to review."

Do not claim tests have passed. Do not claim a preview URL exists. Let the mgmt-bot run the real commands and report back.

---

## Output — preview handoff report

Always return this exact format after a successful build:

```
Phase N build complete — <project-name>

Preview URL: <vercel-preview-url>

What changed:
- <item 1>
- <item 2>
...

What I tested:
- npm run lint ✓
- npm run typecheck ✓
- npm run build ✓
- npm test ✓

What I'd like you to check:
- <specific thing to verify manually on mobile>
- <specific flow to walk through>
- <specific edge case to try>

Known limitations / not done yet:
- <anything phase intentionally excludes>
- <anything deferred to next phase>

Next phase: Phase N+1 — <name from spec>
```

---

## Stop conditions

Stop immediately and report if:
- Spec file not found
- Repo not found
- Any self-test step fails (fix before pushing, not after)
- Push fails
- Phase description is ambiguous (ask Tom before building)

---

## Failure modes

| Situation | Action |
|-----------|--------|
| Spec not found | Stop — "Spec not found. Run app-plan first." |
| Phase N not in spec | Stop — "Phase N not defined in spec. Check the spec or ask Tom." |
| Lint fails | Fix it. Do not push. |
| Typecheck fails | Fix it. Do not push. |
| Build fails | Fix it. Do not push. |
| Tests fail | Fix them. Do not push. |
| Git push rejected | Stop — report exact error. Do not force-push. |
| Vercel preview not generated | Report — "Preview may take a moment. Check Vercel dashboard at https://vercel.com/dashboard" |

**Never push failing code. Never bluff a passing test. Never build out of scope.**
