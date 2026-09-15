---
name: mgmt-bot
description: Use the management-bot file-first dev-command workflow. Use when Tom wants project shell actions executed via the controlled `.dev-cmd.json` mechanism instead of direct exec.
---

# Mgmt Bot

## Goal
Route dev-project shell actions through the controlled management-bot workflow.

## Process
1. Confirm Tom actually wants a dev command run.
2. **Distinguish the control plane first:** verify whether Tom means:
   - the separate **Pi management bot / host-control bot**, or
   - the local project `.dev-cmd.json` workflow.
3. If it is the project `.dev-cmd.json` workflow, write one `.dev-cmd.json` command at a time in the project directory.
4. Wait for confirmation/result before queuing the next command.
5. Keep commands visible and controlled.

## Rules
- Do not use this for unrelated shell work.
- Do not queue commands Tom did not request.
- One command at a time.
- Use this instead of ad hoc git/npm shell flows when the project workflow expects management-bot control.
- **Control-plane distinction rule (MANDATORY):** when Tom says "management bot" / "mgmt-bot" / asks for a `/xxxx` command, do not assume it means OpenClaw Telegram commands or plugin commands. First locate the actual management-bot implementation path. If the request is about the separate Pi control bot, work in that system rather than inventing an OpenClaw command path.
- **No-name-based assumptions:** similarity of names is not enough. Before proposing integration, identify the real code/config surface being extended.

## Mandatory end-of-use review *(Updated: 2026-06-14 22:19)*
After every real use of this skill, do a short explicit pass with Tom on whether anything in the skill itself should be updated.
Treat that review as part of completion, even if the outcome is "no skill changes needed".
