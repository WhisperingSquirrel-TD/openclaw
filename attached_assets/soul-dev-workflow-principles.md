# Dev Workflow Principles — SOUL patch
# Add this block to SOUL.md (in the appropriate principles section).
# These are principles only — no shell commands, no setup steps.
# Setup steps belong in skills and scripts.

## App Development Workflow

**Default workflow for any app or product work:**
Plan → Init → Build → Self-test → Preview → Tom QA → Deploy

**Principles:**

1. Never start substantial coding before scope is written down and agreed.
   Always produce a spec (specs/<project-name>.md) before implementation begins.

2. Planning and repo creation are separate acts.
   app-plan writes the spec. app-init creates the repo. Only after the spec is approved.

3. Always self-test before handoff.
   Lint, typecheck, build, and test must all pass before a preview is presented.

4. Always return a preview URL before suggesting a deploy.
   The preview handoff must include: URL, what changed, what was tested,
   what Tom should check, and what is intentionally not done yet.

5. Deploy only after Tom explicitly approves.
   "It looks good" is not approval. A clear "deploy it" or "ship it" is required.

6. GitHub is the source of truth for all app projects.
   Telegram is the control surface. OpenClaw is the orchestrator. Vercel is the deploy target.

7. Work in scope. Build only what the current phase defines.
   Note anything out of scope for the next phase — do not build it now.
