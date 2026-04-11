# SKILL: Learning — Capture and File Durable Knowledge

## When to use
When something is discovered during a session that should persist beyond it:
- a system behaviour that took effort to work out
- a preference Tom expressed
- a process rule that should always apply
- a fix for a recurring problem

## What NOT to use this for
- Temporary notes (use HEARTBEAT.md)
- Task reminders (use TASKS.md)
- System improvements (use BACKLOG.md)
- Proposed rule changes (use SOUL_PENDING.md)

## Process

### Step 1 — Decide where it belongs
| Type of learning | File |
|---|---|
| Durable fact about system/integrations/Tom's preferences | MEMORY.md |
| Proposed change to operating rules | SOUL_PENDING.md |
| System improvement to implement | BACKLOG.md |
| Action to take | TASKS.md |
| Routing/location change | SYSTEM_MAP.md |

### Step 2 — Write it clearly
- One fact per bullet
- Include enough context to be understood cold (next session, no memory)
- Date stamp if relevant

### Step 3 — Confirm to Tom
- Say what was learned and where it was filed
- Do not just say "noted" — show the write happened

## Example
Tom says: "When Garmin is rate-limited, don't retry."

Action:
1. Write to MEMORY.md: `- Garmin auth: 429 = rate-limited IP. Do NOT retry. Run poller interactively to refresh session after waiting.`
2. Confirm: "Got it — filed to MEMORY.md."
