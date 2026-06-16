---
name: app-init
description: Initialise a new app project after its spec is approved. Creates the GitHub repo, scaffolds from the standard template, stores the canonical repo link, and prepares the GitHub-backed hosted preview path (for example Vercel). Use when Tom says "initialise project X", "init X", "set up the repo for X", or "ready to start building X". Requires an approved spec file. Fails loudly if tokens or prerequisites are missing.
---

# app-init

_Last updated: 2026-06-15 14:41_

**Purpose:** Initialise a project for build — create the GitHub repo, scaffold from template, store the canonical repo details, and prepare the GitHub-backed hosted preview route. This skill runs once per project, after the spec is approved, before any build work begins.

---

## Trigger

Use this skill when Tom says any of:

- "Initialise project X"
- "Init X"
- "Set up the repo for X"
- "Ready to start building X"

**Prerequisite:** A spec file must exist at `~/.openclaw/workspace/specs/<project-name>.md` and Tom must have approved it.

---

## Required inputs

Before starting, confirm you have:

1. **Project name** — must match an existing spec file
2. **GitHub username / org** — where to create the repo (default: Tom's personal account)
3. **Template repo** — the standard Next.js/Tailwind/TS template (default: stored in `~/.openclaw/workspace/reference/template-repo.txt`)
4. **GITHUB_TOKEN** — must be present in `.env`
5. **VERCEL_TOKEN** — must be present in `.env`

If any are missing, stop and report. Do not proceed.

---

## Process

Before starting, state the bounded automation line explicitly:

- L1 may perform the approved initialisation mechanics (checks, repo creation, scaffold, linking, durable recording)
- L1 may not silently change product scope, template choice, repo ownership, hosting strategy, or downstream operator workflow without Tom's approval

### Step 1 — Verify prerequisites

Use the raw sources directly for prerequisite status (`spec` file, `.env`, helper output, repo state). Do not infer readiness from memory or from a previous successful project.

```bash
# Check spec exists
ls ~/.openclaw/workspace/specs/<project-name>.md

# Check tokens
grep -q GITHUB_TOKEN ~/.openclaw/.env || echo "MISSING: GITHUB_TOKEN"
grep -q VERCEL_TOKEN ~/.openclaw/.env || echo "MISSING: VERCEL_TOKEN"
```

If anything is missing: **stop and report clearly. Do not continue.**

### Step 2 — Create GitHub repo

Run the helper script:

```bash
python3 ~/.openclaw/integrations/github/create-repo.py \
  --name <project-name> \
  --template <template-owner>/<template-repo> \
  --private false
```

The script returns the clone URL on success, or an error message on failure.

**If repo creation fails: stop and report the exact error. Do not continue.**

### Step 3 — Clone locally for setup

```bash
cd ~/.openclaw/workspace/projects/
git clone <clone-url>
cd <project-name>
```

### Step 3a — Upgrade Next.js to latest safe version

Vercel hard-blocks deployments on Next.js versions with known CVEs. Upgrade
immediately after cloning so the project is never deployed on a vulnerable version:

```bash
npm install next@latest
```

Confirm the installed version is at least 14.2.25 (14.x) or 15.2.3 (15.x):

```bash
node -e "console.log(require('./node_modules/next/package.json').version)"
```

If `npm install` fails at this point, stop and report. Do not continue.

### Step 4 — Prepare .env.example

Copy from template if not already present. Ensure it lists:

- `NEXT_PUBLIC_APP_URL=`
- Any integration keys the spec calls for

Do not put real secrets into .env.example.

### Step 5 — Prepare GitHub-backed hosted preview route

Link the repo to the hosted preview provider so preview deploys trigger from GitHub pushes:

```bash
npx vercel link --yes --project <project-name> --token $VERCEL_TOKEN
```

If this step fails, stop and report clearly. Do not continue.

### Step 5a — Store canonical downstream linkage

Record the information future build/control steps will need:

- canonical local project path
- canonical GitHub repo URL
- remote name (`origin` unless intentionally different)
- default branch
- hosted preview provider
- how preview URLs are expected to appear after push
- whether the project must be added to the workspace dev-project registry immediately

Minimum durable record: add/update the relevant project note/spec/progress file with the repo URL and preview-hosting route so future sessions do not have to rediscover it.

### Step 6 — Create session journal

Create the `PROGRESS.md` file so that future sessions have a journal to read and write:

```bash
cat > ~/.openclaw/workspace/projects/<project-name>/PROGRESS.md << 'EOF'
# PROGRESS — <project-name>

Session journal. Most recent entry at the top.
Each entry written by L1 at the end of a build session.

---
EOF
```

This file is committed alongside the initial setup and updated after every build phase.

### Step 7 — Commit initial setup

```bash
git add .
git commit -m "chore: initial project setup from template"
git push origin main
```

After push, verify that:

- the GitHub remote is the canonical source for hosted preview builds
- the repo URL is stored in a durable project file
- the downstream control-plane/GUI path knows which repo this project belongs to
- the proof artifacts for successful init are captured clearly enough that a later resume can verify them without guesswork (for example repo URL, local path, branch, link status, initial commit/push evidence)

---

## Output

Report to Tom:

```
Project <name> initialised.

Repo: https://github.com/<owner>/<project-name>
Hosted preview: connected to GitHub-backed deploy flow (will generate preview URL on next push)
Spec: ~/.openclaw/workspace/specs/<project-name>.md
Canonical repo link + downstream route: recorded for future build/control-plane use

Ready to build. Tell me: "Build phase 1" to start.
```

---

## Stop conditions

Stop immediately and report if:

- Spec file not found
- GITHUB_TOKEN missing
- VERCEL_TOKEN missing
- Repo creation fails (API error, name conflict, token scope issue)
- Clone fails
- Vercel link fails

**Never silently continue past a failure. Report the exact error, the step that failed, and what Tom needs to do to fix it.**

---

## Failure modes

| Situation               | Action                                                                                    |
| ----------------------- | ----------------------------------------------------------------------------------------- |
| GITHUB_TOKEN missing    | Stop — "GITHUB_TOKEN not found in .env. Add it and retry."                                |
| VERCEL_TOKEN missing    | Stop — "VERCEL_TOKEN not found in .env. Add it and retry."                                |
| Repo name already taken | Stop — "Repo <name> already exists. Choose a different name or delete the existing one."  |
| GitHub API 401          | Stop — "GitHub token rejected. Check token scope (needs: repo)."                          |
| GitHub API 422          | Stop — "Repo creation failed (validation error). Check token scope and repo name."        |
| Template repo not found | Stop — "Template repo not found. Check ~/.openclaw/workspace/reference/template-repo.txt" |
| Vercel link fails       | Stop — report exact error from Vercel CLI                                                 |
| projects/ dir missing   | Create it: `mkdir -p ~/.openclaw/workspace/projects/`                                     |
