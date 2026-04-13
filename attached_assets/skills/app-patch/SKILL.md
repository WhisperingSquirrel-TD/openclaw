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

Do NOT run git commands directly — write a dev-cmd request for the mgmt-bot.

If the project directory does not exist yet:

```python
import json, pathlib, datetime
p = pathlib.Path.home() / ".openclaw/workspace/projects/{repo}/.dev-cmd.json"
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps({
    "project":      "{repo}",
    "operation":    "git_clone",
    "args":         {"url": "https://github.com/WhisperingSquirrel-TD/{repo}.git", "branch": "main"},
    "message":      "Clone {repo} for patch work",
    "triggered_at": datetime.datetime.utcnow().isoformat()
}))
print("Dev-cmd written — waiting for mgmt-bot to clone repo (~30 s)…")
```

If the project directory already exists, write `git_pull` instead:

```python
import json, pathlib, datetime
p = pathlib.Path.home() / ".openclaw/workspace/projects/{repo}/.dev-cmd.json"
p.write_text(json.dumps({
    "project":      "{repo}",
    "operation":    "git_pull",
    "args":         {},
    "message":      "Pull latest before patching {repo}",
    "triggered_at": datetime.datetime.utcnow().isoformat()
}))
print("Dev-cmd written — waiting for mgmt-bot to pull (~30 s)…")
```

**Wait for Telegram confirmation from the mgmt-bot before continuing.**

---

## Phase 3 — Create a feature branch

Branch name format: `patch/{short-slug-of-change}`

```python
import json, pathlib, datetime
p = pathlib.Path.home() / ".openclaw/workspace/projects/{repo}/.dev-cmd.json"
p.write_text(json.dumps({
    "project":      "{repo}",
    "operation":    "git_branch",
    "args":         {"branch": "patch/{short-slug}"},
    "message":      "Create branch for: {change_description}",
    "triggered_at": datetime.datetime.utcnow().isoformat()
}))
print("Dev-cmd written — waiting for mgmt-bot to create branch (~30 s)…")
```

**Wait for Telegram confirmation before editing any files.**

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

## Phase 5 — Commit and push

Do NOT run git commands directly. Write a `git_commit_push` dev-cmd:

```python
import json, pathlib, datetime
p = pathlib.Path.home() / ".openclaw/workspace/projects/{repo}/.dev-cmd.json"
p.write_text(json.dumps({
    "project":      "{repo}",
    "operation":    "git_commit_push",
    "args":         {
        "message": "patch: {short description}\n\nRequested via Telegram.\nChange: {full change description}",
        "branch":  "patch/{short-slug}"
    },
    "message":      "Commit and push patch changes",
    "triggered_at": datetime.datetime.utcnow().isoformat()
}))
print("Dev-cmd written — mgmt-bot will commit and push (~30 s)…")
```

**Wait for Telegram confirmation before writing the `.pending-dev-run` trigger.**

---

## Phase 6 — Write trigger file to kick off auto-build

After pushing, write a trigger file so the mgmt-bot picks it up automatically
within 30 seconds and runs install → build → Vercel preview without Tom needing
to type anything:

```bash
python3 -c "
import json, pathlib, datetime
p = pathlib.Path('$HOME/.openclaw/workspace/projects/{repo}/.pending-dev-run')
p.write_text(json.dumps({
    'project': '{repo}',
    'change': '{change_description}',
    'branch': '{branch}',
    'triggered_at': datetime.datetime.utcnow().isoformat()
}))
print('Trigger written:', p)
"
```

Then tell Tom:

> "Changes are pushed to `{BRANCH}` and the build has been triggered automatically.
> You'll get a Vercel preview URL in Telegram within ~60 seconds.
> Review it and reply `deploy {repo}` to go live or `reject {repo}` to discard."

Do not claim tests have passed. Do not claim a preview URL exists. The mgmt-bot runs the real commands.

---

## Phase 8 — Wait for QA approval

**Do not proceed until the user explicitly replies with one of:**
- `deploy {repo}` → continue to Phase 9
- `reject {repo}` → run Phase 9R (reject)

Any other reply: ask for clarification. Do not auto-deploy.

---

## Phase 9 — Deploy (on approval)

Do NOT run git or vercel commands directly. Use the dev-cmd queue.

**Step 1 — merge the branch into main:**

```python
import json, pathlib, datetime
p = pathlib.Path.home() / ".openclaw/workspace/projects/{repo}/.dev-cmd.json"
p.write_text(json.dumps({
    "project":      "{repo}",
    "operation":    "git_merge_main",
    "args":         {"branch": "patch/{short-slug}"},
    "message":      "Merge approved patch into main",
    "triggered_at": datetime.datetime.utcnow().isoformat()
}))
print("Dev-cmd written — mgmt-bot will merge branch (~30 s)…")
```

**Wait for Telegram confirmation of the merge.**

**Step 2 — trigger production build:**

```python
import json, pathlib, datetime
p = pathlib.Path.home() / ".openclaw/workspace/projects/{repo}/.pending-dev-run"
p.write_text(json.dumps({
    "project":      "{repo}",
    "change":       "Production deploy — patch/{short-slug} merged",
    "triggered_at": datetime.datetime.utcnow().isoformat()
}))
print("Build trigger written — Vercel preview incoming (~60 s)…")
```

**Step 3 — clean up the branch:**

```python
import json, pathlib, datetime
p = pathlib.Path.home() / ".openclaw/workspace/projects/{repo}/.dev-cmd.json"
p.write_text(json.dumps({
    "project":      "{repo}",
    "operation":    "git_delete_branch",
    "args":         {"branch": "patch/{short-slug}"},
    "message":      "Delete merged patch branch",
    "triggered_at": datetime.datetime.utcnow().isoformat()
}))
```

Then notify Tom:

> "Branch merged into main and build triggered.
> Vercel preview will arrive in ~60 seconds.
> Reply `deploy {repo}` to push to production."

---

## Phase 9R — Reject (on rejection)

Write `git_delete_branch` to discard the branch:

```python
import json, pathlib, datetime
p = pathlib.Path.home() / ".openclaw/workspace/projects/{repo}/.dev-cmd.json"
p.write_text(json.dumps({
    "project":      "{repo}",
    "operation":    "git_delete_branch",
    "args":         {"branch": "patch/{short-slug}"},
    "message":      "Delete rejected patch branch",
    "triggered_at": datetime.datetime.utcnow().isoformat()
}))
```

Notify Tom:

> "Change discarded. Branch patch/{short-slug} deleted. {repo} is unchanged."

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
