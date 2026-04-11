# ORGANIZATION.md — Workspace Design Rules

## Principle
Files are the source of truth. Telegram is the control surface. Skills are the process layer.
Never rely on chat memory when a file should hold the answer.

## File hierarchy
```
~/.openclaw/workspace/
  USER.md           — Tom's profile, preferences, priorities
  SYSTEM_MAP.md     — routing: where everything lives and what it does
  ORGANIZATION.md   — this file: design rules
  TASKS.md          — active non-code action items
  BACKLOG.md        — technical/system improvements queue
  PLAN.md           — today's live plan
  MEMORY.md         — persistent learnings across sessions
  SOUL_PENDING.md   — proposed SOUL changes (never auto-promote)
  HEARTBEAT.md      — session continuity, open loops
  SYSTEM_HEALTH.md  — cron/poller health status

  skills/           — repeatable process logic (each has SKILL.md)
  reference/        — heavier support material, rarely changes
  memory/           — log files from pollers/integrations
```

## Rules for files
- **SOUL.md** is encrypted. Never create a plaintext SOUL.md in the workspace.
- **SOUL_PENDING.md** is a staging area — never promote to SOUL automatically.
- **TASKS.md** = action items. **BACKLOG.md** = improvements. Keep them separate.
- **MEMORY.md** = durable learnings. HEARTBEAT.md = session continuity. Different purposes.
- Skills go in `skills/<name>/SKILL.md`. One skill per folder.
- Reference files go in `reference/`. Only for material that is stable and rarely changes.

## Rules for updates
- When you learn something durable: write it to MEMORY.md.
- When a process needs improving: write it to BACKLOG.md.
- When a proposed rule change needs review: write it to SOUL_PENDING.md, not SOUL.md.
- When a task is done: remove it from TASKS.md.
- Always update SYSTEM_MAP.md when a new file, skill, or integration is added.

## Rules for coding work
- Use subagents for multi-step, long, or isolated coding tasks.
- Write results back to a file — never leave coding work only in chat.
- Always update TASKS.md or BACKLOG.md to reflect what was done.
- Push changes to GitHub after any significant code session.

## File size discipline
- SOUL.md equivalent: < 4KB
- HEARTBEAT.md: < 2KB (session-scoped, reset each session)
- MEMORY.md: < 20KB (trim oldest when approaching limit)
- TASKS.md / BACKLOG.md: no hard limit but review regularly
