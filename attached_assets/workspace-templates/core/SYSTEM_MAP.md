# SYSTEM_MAP.md — Where Everything Lives

_This is the routing layer. When you need to find something, check here first._

## Workspace root
`~/.openclaw/workspace/`

## Core control files
| File | Purpose |
|---|---|
| USER.md | Tom's profile, priorities, preferences |
| ORGANIZATION.md | Workspace design rules, file hierarchy |
| SYSTEM_MAP.md | This file — routing guide |
| TASKS.md | Active action items (non-code) |
| BACKLOG.md | Technical/system improvements queue |
| PLAN.md | Today's live plan |
| MEMORY.md | Persistent learnings across sessions |
| HEARTBEAT.md | Session continuity, open loops |
| SYSTEM_HEALTH.md | Cron/poller health alerts |
| SOUL_PENDING.md | Proposed SOUL rule changes (review only) |

## Integration data files (written by pollers)
| File | Written by | Content |
|---|---|---|
| GARMIN_DAILY.md | Garmin poller (09:00) | Resting HR, HRV, sleep, stress, body battery, steps |
| GARMIN_ARCHIVE.md | Garmin poller | Rolling 28-day health history |
| SHAREPOINT_INDEX.md | SharePoint cache poller (every 15 min) | SharePoint folder/file index |
| SHAREPOINT_RESULT.md | SharePoint queue processor | Results of queued SP operations |
| STACKSTONE_REPORTS.md | Report poller (every 5 min) | Sent networking report log (90 days) |
| STACKSTONE_ENQUIRIES.md | Enquiry poller (every 2 min) | Inbound lead log (90 days) |

## Skills (process logic)
`~/.openclaw/workspace/skills/`
| Skill | Path | When to use |
|---|---|---|
| Learning | skills/learning/SKILL.md | Capturing and filing durable learnings |
| Daily plan | skills/daily-plan/SKILL.md | Building today's plan |
| Briefing | skills/briefing/SKILL.md | Morning briefing format |
| Weekly review | skills/weekly-review/SKILL.md | Friday system review |
| Expenses | skills/expenses/SKILL.md | Logging and reviewing expenses |
| Coding | skills/coding/SKILL.md | Telegram-controlled coding workflow |

## Reference files
`~/.openclaw/workspace/reference/`
| File | Content |
|---|---|
| CRONS.md | All cron jobs, schedules, and log paths |
| POLLERS.md | All pollers, what they do, and how to test them |
| AI-INTEL-OPTIONS.md | AI capability options and subagent/ACP guidance |

## Integrations (code lives in `~/.openclaw/integrations/`)
| Integration | Path | What it does |
|---|---|---|
| Microsoft 365 | integrations/microsoft/ | Email poll, calendar, send, SharePoint |
| Gmail | integrations/google/ | Gmail inbox poll |
| Garmin | integrations/garmin/ | Daily health data |
| SharePoint | integrations/microsoft/ | Document management via queue |
| Stackstone reports | integrations/stackstone/ | Report email delivery |
| Stackstone enquiries | integrations/stackstone/ | Inbound lead alerting |
| CRM | integrations/crm/ | Lead import from prospects/ CSVs |
| Health check | integrations/health/ | System/cron health monitoring |
| Management bot | integrations/mgmt-bot/ | Telegram management commands |

## Cron schedule (summary)
| Time | Job |
|---|---|
| 04:00 | Provider reset → openai-codex/gpt-5.4 |
| 06:55 | System health check |
| 08:00 | CRM lead import |
| 09:00 | Garmin health poller |
| Every 1 min | SharePoint queue processor |
| Every 2 min | Stackstone enquiry poller |
| Every 5 min | Stackstone report poller |
| Every 15 min | SharePoint cache refresh |

## Management bot commands (via Telegram)
`/status` `/anthropic` `/openai` `/codex` `/restart` `/garmin`
`/pull` `/install` `/reboot` `/health` `/logs` `/disk` `/soul` `/cancel` `/help`

## Key paths on Pi
| Purpose | Path |
|---|---|
| OpenClaw config | ~/.openclaw/openclaw.json |
| Environment variables | ~/.openclaw/.env |
| Encrypted SOUL vault | ~/.openclaw/vault/SOUL.md.enc |
| Workspace | ~/.openclaw/workspace/ |
| Integration scripts | ~/.openclaw/integrations/ |
| Git repo (forked OpenClaw) | ~/openclaw/ |
| GitHub repo | github.com/WhisperingSquirrel-TD/openclaw |
