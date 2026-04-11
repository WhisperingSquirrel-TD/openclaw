# SKILL: Coding — Telegram-Controlled Coding Workflow

## When to use
When Tom wants to plan, review, or trigger coding work from Telegram.

## The two modes

### Mode 1 — Quick edits (main session)
For small, specific changes:
- "Add X to the cron schedule"
- "Fix the typo in Y file"
- "Update the config to use Z"

Handle directly in the main session. Write the change. Confirm it's done.

### Mode 2 — Bigger work (subagent)
For anything multi-step, slow, or better isolated:
- Audits and reviews
- Refactoring a whole integration
- Writing a new poller from scratch
- Comparing approaches

Use a subagent. See below.

## How to trigger a subagent for coding

Tom can say:
- "Use a subagent to audit the SharePoint poller"
- "Run this as a subagent: refactor poll-garmin.py to handle X"
- Or just: "Do this in the background"

Or use the slash command directly:
```
/subagents spawn l1 <task description>
```

The subagent runs in isolation, completes the task, and posts results back to Telegram.

## Workflow for any coding task

### Step 1 — Understand the task
Before writing any code:
- Check SYSTEM_MAP.md for where the relevant files live
- Check BACKLOG.md and TASKS.md for related context
- Check MEMORY.md for known gotchas

### Step 2 — Plan
For anything bigger than a one-line fix, state the plan before coding.
Tom can approve, redirect, or cancel before work starts.

### Step 3 — Code
Write the change. Keep it minimal and targeted.
Follow existing patterns in the codebase.

### Step 4 — Verify
After any change:
- Check the file was actually written correctly
- For pollers: note the manual test command
- For cron changes: show the new crontab entry

### Step 5 — Record
- Update TASKS.md or BACKLOG.md to mark the item done
- Update SYSTEM_MAP.md if a new file or integration was added
- Add any learnings to MEMORY.md

### Step 6 — Push
Remind Tom to push to GitHub:
```
bash scripts/push-to-github.sh
```
Then pull to Pi:
```
git -C ~/openclaw pull && bash ~/openclaw/attached_assets/install-forked-openclaw.sh
```
Or use the targeted deploy command for the specific file changed.

## Key file locations (for coding tasks)
| What | Path |
|---|---|
| Pollers | ~/openclaw/attached_assets/integrations/ |
| Install script | ~/openclaw/attached_assets/install-forked-openclaw.sh |
| Management bot | ~/openclaw/attached_assets/integrations/mgmt-bot/mgmt-bot.py |
| Workspace templates | ~/openclaw/attached_assets/workspace-templates/ |
| Provision script | ~/openclaw/attached_assets/provision-workspace.sh |
| Utility scripts | ~/openclaw/scripts/ |
