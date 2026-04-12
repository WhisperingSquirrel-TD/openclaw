---
id: app-patch
version: 1.0.0
trigger: "Patch project {repo} [: {change_description}]"
phase: patch
stack: any
requires:
  env:
    - GITHUB_TOKEN
    - VERCEL_TOKEN
    - VERCEL_SCOPE
  files:
    - ~/.openclaw/.env
---

# app-patch — Modify an Existing Repo via Telegram

Use this skill when the user wants to make changes to an **existing GitHub repository**
rather than starting a new app from the template.

---

## Trigger phrases (examples)

- "Patch project stackstone-website: update the pricing page"
- "Patch WhisperingSquirrel-TD/stackstone-website: fix the nav menu on mobile"
- "Make a change to stackstone-website — add a contact form"

If the user gives a bare repo name (e.g. `stackstone-website`) assume the owner is
`WhisperingSquirrel-TD` unless they specify otherwise.

---

## Failure modes — check these before proceeding

| Condition | Action |
|---|---|
| Repo does not exist or GITHUB_TOKEN lacks access | Stop. Tell the user the exact repo path you tried and ask them to confirm it |
| Change description is ambiguous | Ask one clarifying question before touching any file |
| No Vercel project linked to this repo | Warn the user — preview URL will not be available; ask whether to proceed anyway |
| Self-test fails | Do NOT continue to the preview/deploy phase. Report the failure, show the error, ask the user how to proceed |
| User has not approved preview | Never run deploy without explicit approval |

---

## Phase 1 — Understand the change

1. Parse the repo name and change description from the user's message.
2. If the change description is vague (e.g. "make it better"), ask one focused question:
   *"What specifically should change — copy, layout, functionality, or something else?"*
3. Write a one-paragraph plain-English summary of what you will change and **why**,
   then ask the user to confirm before touching any code:
   > "Here's what I'll do: [summary]. Shall I go ahead?"
4. Wait for confirmation. Do not proceed until you have it.

---

## Phase 2 — Clone or update the repo

```bash
# Load env
set -a && source ~/.openclaw/.env && set +a

OWNER="WhisperingSquirrel-TD"   # override if user specified a different owner
REPO="{repo}"
WORKSPACE="$HOME/.openclaw/workspace/projects/$REPO"

# Pull if already cloned, clone if not
if [ -d "$WORKSPACE/.git" ]; then
  git -C "$WORKSPACE" pull
else
  git clone "https://$GITHUB_TOKEN@github.com/$OWNER/$REPO.git" "$WORKSPACE"
fi
```

---

## Phase 3 — Create a feature branch

Branch name format: `patch/{short-slug-of-change}`

Examples:
- `patch/update-pricing-page`
- `patch/fix-mobile-nav`
- `patch/add-contact-form`

```bash
BRANCH="patch/{short-slug}"
git -C "$WORKSPACE" checkout -b "$BRANCH"
```

---

## Phase 4 — Make the change (Superpowers discipline)

Apply the **Superpowers build discipline** from `app-build`:

- Work **one file at a time**
- State explicit acceptance criteria for each file before editing it
- No silent fallbacks — if something is unclear, stop and ask
- No placeholder content — every change must be real and complete
- After each file: read it back and verify it matches the acceptance criteria

Common change types and what to watch for:

| Change type | Watch for |
|---|---|
| Copy / content | Preserve existing tone and style unless told otherwise |
| Layout / CSS | Check mobile and desktop breakpoints |
| New component | Must connect to existing routing/navigation if user-facing |
| API / data | Never hardcode credentials; read from env |
| Config change | Check if it affects build or deploy pipeline |

---

## Phase 5 — Self-test

Run whatever test/lint commands the repo exposes:

```bash
cd "$WORKSPACE"

# Try these in order — skip any that don't exist
npm run lint        2>/dev/null || true
npm run typecheck   2>/dev/null || true
npm run build       2>/dev/null || true
npm test            2>/dev/null || true
```

If **any command that exists** exits with a non-zero code:
- Stop immediately
- Report the exact error to the user
- Do NOT commit, push, or deploy
- Ask the user: "Self-test failed. Do you want me to fix the error or stop here?"

---

## Phase 6 — Commit and push

```bash
cd "$WORKSPACE"
git add -A
git commit -m "patch: {short description of change}

Requested via Telegram.
Change: {full change description}"
git push origin "$BRANCH"
```

---

## Phase 7 — Vercel preview

```bash
cd "$WORKSPACE"
vercel --token "$VERCEL_TOKEN" --scope "$VERCEL_SCOPE" 2>&1 | tee /tmp/vercel-patch-preview.log
PREVIEW_URL=$(grep -oP 'https://[^\s]+\.vercel\.app' /tmp/vercel-patch-preview.log | tail -1)
```

Send the preview URL to the user on Telegram:

> "Patch is ready for your review.
> Preview: {PREVIEW_URL}
> Branch: {BRANCH}
> Changes: {short summary}
>
> Reply 'deploy {repo}' to merge and go live, or 'reject {repo}' to discard."

---

## Phase 8 — Wait for QA approval

**Do not proceed until the user explicitly replies with one of:**
- `deploy {repo}` → continue to Phase 9
- `reject {repo}` → run Phase 9R (reject)

Any other reply: ask for clarification. Do not auto-deploy.

---

## Phase 9 — Deploy (on approval)

```bash
cd "$WORKSPACE"

# Merge branch into main
git checkout main
git merge "$BRANCH" --no-ff -m "Merge $BRANCH into main (approved via Telegram)"
git push origin main

# Deploy to production
vercel --prod --token "$VERCEL_TOKEN" --scope "$VERCEL_SCOPE"
```

Notify the user:

> "Deployed. {repo} is now live on main.
> Branch {BRANCH} has been merged."

---

## Phase 9R — Reject (on rejection)

```bash
cd "$WORKSPACE"
git checkout main
git branch -D "$BRANCH"
git push origin --delete "$BRANCH" 2>/dev/null || true
```

Notify the user:

> "Change discarded. Branch {BRANCH} deleted. {repo} is unchanged."

---

## State file

Write a patch state file after Phase 3 so the workflow survives a bot restart:

```
~/.openclaw/workspace/projects/{repo}/.patch-state.json
```

```json
{
  "repo": "{repo}",
  "branch": "{branch}",
  "change": "{change_description}",
  "phase": "preview|approved|rejected",
  "preview_url": "{url}",
  "started_at": "{iso8601}"
}
```

Update the `phase` field at each phase transition.
