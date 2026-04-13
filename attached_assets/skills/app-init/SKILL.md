---
name: app-init
description: Initialise a new app project after its spec is approved. Creates the GitHub repo, scaffolds from the standard template, prepares Vercel preview deployment. Use when Tom says "initialise project X", "init X", "set up the repo for X", or "ready to start building X". Requires an approved spec file. Fails loudly if tokens or prerequisites are missing.
---

# app-init

**Purpose:** Initialise a project for build — create the GitHub repo, scaffold from template, prepare Vercel preview deployment. This skill runs once per project, after the spec is approved, before any build work begins.

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

### Step 1 — Verify prerequisites

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

### Step 5 — Prepare Vercel preview deployment

Link the repo to Vercel so preview deploys trigger automatically on push:
```bash
npx vercel link --yes --project <project-name> --token $VERCEL_TOKEN
```

If this step fails, stop and report clearly. Do not continue.

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

---

## Output

Report to Tom:
```
Project <name> initialised.

Repo: https://github.com/<owner>/<project-name>
Vercel preview: connected (will generate preview URL on next push)
Spec: ~/.openclaw/workspace/specs/<project-name>.md

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

| Situation | Action |
|-----------|--------|
| GITHUB_TOKEN missing | Stop — "GITHUB_TOKEN not found in .env. Add it and retry." |
| VERCEL_TOKEN missing | Stop — "VERCEL_TOKEN not found in .env. Add it and retry." |
| Repo name already taken | Stop — "Repo <name> already exists. Choose a different name or delete the existing one." |
| GitHub API 401 | Stop — "GitHub token rejected. Check token scope (needs: repo)." |
| GitHub API 422 | Stop — "Repo creation failed (validation error). Check token scope and repo name." |
| Template repo not found | Stop — "Template repo not found. Check ~/.openclaw/workspace/reference/template-repo.txt" |
| Vercel link fails | Stop — report exact error from Vercel CLI |
| projects/ dir missing | Create it: `mkdir -p ~/.openclaw/workspace/projects/` |
