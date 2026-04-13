---
name: mgmt-bot
description: Reference for the OpenClaw management bot capabilities. Read this before any dev workflow task — it defines what shell operations you can request and exactly how to request them. Never use exec for dev operations; always use this queue.
---

# mgmt-bot — Dev Command Queue Reference

The OpenClaw management bot is a separate Telegram bot running on the Pi.
It handles all shell execution for dev workflow tasks. **You never need exec
for coding work — write a `.dev-cmd.json` request file instead.**

---

## Why this exists

You do not have exec access for dev operations. Instead:
- You write a structured JSON request file
- The mgmt-bot reads it within 30 seconds and runs the whitelisted operation
- Results are reported back to Tom via Telegram
- Tom can pause/resume the queue at any time

This gives Tom full visibility and control without requiring TOTP for every
git commit or npm install.

---

## How to request a dev operation

Write a file to:
```
~/.openclaw/workspace/projects/<project-name>/.dev-cmd.json
```

Format:
```json
{
  "project":      "<project-name>",
  "operation":    "<operation-name>",
  "args":         { },
  "message":      "Plain English description of what this does and why",
  "triggered_at": "<ISO 8601 timestamp>"
}
```

The mgmt-bot processes it within 30 seconds and deletes the file.
**Only one `.dev-cmd.json` per project at a time.** Write the next one
after you receive confirmation in Telegram.

---

## Supported operations

### `git_clone`
Clone a GitHub repo into `workspace/projects/<project>`.

```json
{
  "operation": "git_clone",
  "args": {
    "url":    "https://github.com/WhisperingSquirrel-TD/my-repo.git",
    "branch": "main"
  }
}
```
- URL must start with `https://github.com/`
- `branch` defaults to `main` if omitted

---

### `git_pull`
Pull latest from origin in the project directory.

```json
{
  "operation": "git_pull",
  "args": {}
}
```

---

### `git_branch`
Create and checkout a new branch.

```json
{
  "operation": "git_branch",
  "args": { "branch": "patch/fix-mobile-nav" }
}
```
- Branch must contain a `/` (e.g. `patch/`, `feature/`, `fix/`)

---

### `git_commit_push`
Stage all changes, commit with a message, push to origin.

```json
{
  "operation": "git_commit_push",
  "args": {
    "message": "feat: add contact form",
    "branch":  "main"
  }
}
```
- `branch` is optional — defaults to current HEAD
- Always call this **after** you have finished writing your code changes

---

### `git_merge_main`
Merge a feature branch into main and push.

```json
{
  "operation": "git_merge_main",
  "args": { "branch": "patch/fix-mobile-nav" }
}
```
- Only call this after Tom has approved the preview

---

### `git_delete_branch`
Delete a branch locally and on remote.

```json
{
  "operation": "git_delete_branch",
  "args": { "branch": "patch/fix-mobile-nav" }
}
```

---

### `npm_install`
Run `npm install` from the existing `package.json`.

```json
{
  "operation": "npm_install",
  "args": {}
}
```

---

### `npm_upgrade`
Install or upgrade a specific package.

```json
{
  "operation": "npm_upgrade",
  "args": { "package": "next@latest" }
}
```
- Package arg must be a valid npm package identifier (e.g. `next@latest`, `tailwindcss@3.4.0`)
- No shell characters allowed

---

### `npm_run`
Run a named npm script.

```json
{
  "operation": "npm_run",
  "args": { "script": "build" }
}
```
- Only these scripts are allowed: `build`, `lint`, `typecheck`, `type-check`, `test`

---

## Typical app-patch workflow

1. Receive the task from Tom
2. Clone or pull the repo via dev-cmd queue
3. Write a `.dev-cmd.json` for `git_branch` to create a feature branch
4. **Edit the files yourself** — file writes do not need exec or the queue
5. Write a `.dev-cmd.json` for `git_commit_push` once code is ready
6. Write a `.pending-dev-run` trigger file — mgmt-bot builds and deploys Vercel preview
7. Tell Tom: "Preview incoming in ~60 seconds"
8. Wait for Tom's approval (`deploy <project>` or `reject <project>`)
9. On approval: write `.dev-cmd.json` for `git_merge_main`
10. Write `.dev-cmd.json` for `git_delete_branch` to clean up

---

## Upgrading a package (e.g. Next.js)

Do NOT edit `package.json` manually and do NOT use exec.
Use `npm_upgrade`:

```json
{
  "project":   "george-dean-portfolio",
  "operation": "npm_upgrade",
  "args":      { "package": "next@latest" },
  "message":   "Upgrade Next.js to resolve Vercel security block",
  "triggered_at": "2026-04-13T10:00:00"
}
```

Then write `.pending-dev-run` to trigger rebuild and Vercel preview.

---

## Tom's queue controls (Telegram)

| Command         | Effect                                              |
|-----------------|-----------------------------------------------------|
| `/dev-queue`    | Show all pending dev commands                       |
| `/dev-pause`    | Stop auto-executing dev commands (queue still fills)|
| `/dev-resume`   | Resume auto-execution, process any pending now      |

---

## Rules

- **Never use exec for git, npm, or node operations** — always use this queue
- **One command at a time** — wait for Telegram confirmation before writing the next
- **Never write commands Tom didn't ask for** — only queue what was explicitly requested
- **Never queue `git_merge_main` or `git_delete_branch` without Tom's explicit approval**
