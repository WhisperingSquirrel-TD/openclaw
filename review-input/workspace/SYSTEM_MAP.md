# SYSTEM_MAP.md — Where Things Live

_Last updated: 2026-08-16 17:16 BST_

Lightweight routing map. Use this to find the right governing file or detailed reference.
Do not turn this into a dump of full schedules, poller configs, or brand assets.

---

## Design authority

| File | Purpose | Use when |
|---|---|---|
| `ORGANIZATION.md` | Governing organisation design | Structural/placement decisions |
| `SYSTEM_MAP.md` | Routing map | Find things |
| `AGENTS.md` | Session bootstrap | Start |
| `FILE-AUDIT.md` | Structural audit / cleanup working file | Auditing or cleanup decisions |
| `SOUL_PENDING.md` | Proposed SOUL/runtime changes awaiting Tom review | Staging SOUL-level changes |

**Protected policy note:** SOUL / constitutional rules are runtime-provided protected policy, not a normal workspace markdown file.

---

## Core working files

| File | Purpose | Notes |
|---|---|---|
| `USER.md` | Facts about Tom | Lightweight personal reference |
| `MEMORY.md` | Curated long-term operating memory | Main-session memory layer |
| `HEALTH.md` | Governing health support file | Sleep → nutrition → exercise/recovery → repeatability |
| `TASKS.md` | Non-code action tracking | Admin / deliverables |
| `BACKLOG.md` | Technical / coding work | Scripts, system fixes, Replit work |
| `L1-IMPROVEMENTS.md` | Non-breakage L1 improvement backlog | Behaviour, workflow, quality, cost improvements |
| `PLAN.md` | Current working plan | Ephemeral daily plan |
| `WEEK_PLAN.md` | Weekly plan / structure context | Used by daily planning when present |
| `TRAINING_NOTES.md` | Manual companion log for gym/training type notes that Garmin cannot infer well | Used by health support + morning standup |
| `GARMIN_INTRADAY.md` | Compact intraday Garmin state (body battery + movement + latest activity) | Used by health support; designed to stay token-light |
| `contacts.md` | Trusted contact reference | Check before asking for contact details |
| `ACTIONED.md` | Suppression list for already-handled items | Used by inbox/WhatsApp checking |
| `seer-expenses.md` | Legacy/supporting SEER expense evidence | Preserve as read-only supporting evidence during the SQLite reconciliation; do not treat it as an accounting writer |
| `/home/tomdean88/pi-services/seer-finance/data/expense-ledger.sqlite3` | SEER operational expense database + finance ledger | Expense records/candidates only in `expenses`; confirmed income and high-confidence expenses belong in `finance_transactions`; see the finance design before writes |
| `/home/tomdean88/pi-services/seer-finance/transactions.json` | Legacy finance evidence archive during reconciliation | Preserve and reconcile against primary Tide evidence; it is not a routine writer once SQLite ingress is proved |

---

## Operational feeds

| File | Purpose | Detailed reference |
|---|---|---|
| `MICROSOFT_INBOX.md` / `MICROSOFT_EXTERNAL.md` | Outlook email feeds | `reference/POLLERS.md` |
| `GMAIL_INBOX.md` / `GMAIL_EXTERNAL.md` | Gmail email feeds | `reference/POLLERS.md` |
| `OUTLOOK_CALENDAR.md` / `GOOGLE_CALENDAR.md` | Calendar feeds | `reference/POLLERS.md` |
| `GARMIN_DAILY.md` / `GARMIN_ARCHIVE.md` | Recovery / training context | `reference/POLLERS.md` |
| `STACKSTONE_LEADS.md` | Website activity feed | `reference/POLLERS.md` |
| `STACKSTONE_REPORTS.md` | Rolling website report-send log | `reference/POLLERS.md` |
| `STACKSTONE_ENQUIRIES.md` | Rolling website enquiry log | `reference/POLLERS.md` |
| `WHATSAPP_RECENT.md` | Rolling recent WhatsApp feed | `reference/POLLERS.md` |
| `TEAMS_RECENT.md` | Rolling read-only Microsoft Teams visibility feed for chats and selected channels only; not a Teams bot and not meeting capture | `reference/POLLERS.md` + `reference/TEAMS-INFORMATION-FLOW-PLAN.md` |
| `WHATSAPP_LOG.md` | Full WhatsApp archive | Avoid for routine checks |
| `SYSTEM_HEALTH.md` | System health summary, including poller failures plus repo-push/backup freshness visibility | `reference/POLLERS.md` |
| `INVOICE_TRACKER.md` / `INVOICE_TRACKER.json` | Read-only local mirror of SharePoint invoice tracker | `reference/POLLERS.md` |

---

## Business systems

| File / area | Purpose | Notes |
|---|---|---|
| `stackstone/crm.md` | Stackstone CRM summary layer | Canonical local summary file |
| `stackstone/partnerships.md` | Strategic partner summary layer | Investors, introducers, referrers, collaboration partners |
| SharePoint | Rich account/opportunity source of truth | Use SharePoint skills/queue flow; housekeeping is async via processor, see `reference/POLLERS.md` |
| `stackstone/brand/README.md` | Brand asset reference | Keep brand detail there, not in this map |
| `stackstone/reference/sales/` | Stackstone reusable sales positioning / outreach playbooks | Durable sales/reference home |
| `stackstone/reference/sales/SANTANDER-X-AWARDS-ROUND-2-WORKING-DRAFT.md` | Live Santander X working draft | One-off working file |

---

## Active project workspaces

| Path | Purpose | Notes |
|---|---|---|
| `projects/workspace-control-panel/` | Workspace Control Panel + task-system runtime | Resume first; then use `app-patch`/`app-test`. |
| `/home/tomdean88/pi-services/ai-briefing-outbound-service/` | Canonical AI-briefing outbound service | Start with `README.md`; Pi-native. |
| `projects/ai-briefing-outbound-runner/` | Legacy outbound-runner staging copy | Transitional reference only. |
| `projects/linkedin-message-mirror/` | Read-only LinkedIn message mirror | Start with `README.md`. |

## Detailed references

Use this as the routing spine; fuller catalogues live in `reference/REFERENCE-INDEX.md`.

| Area | Go here |
|---|---|
| Pollers, feeds, expenses | `reference/POLLERS.md`; `reference/EXPENSE-SIGNAL-HANDLING.md`; `reference/EXPENSE-INTAKE-RELIABILITY-PLAN.md` for the active all-mirror expense-intake repair; `reference/SEER-EXPENSE-OPERATIONAL-LEDGER.md` for the live SQLite expense/finance boundary, holding tray, Tide-led reconciliation and controlled migration; `reference/finance/reconciliations/Tide-2026-03-18-to-2026-08-08-reconciliation.md` for the current primary-source reconciliation findings and open cutover gates |
| Pi backup/recovery | `reference/PI-PORTABILITY-BACKUP-PLAN.md`; `reference/PI-RESTORE-RUNBOOK.md` |
| Inbound monitoring/routing | `reference/INBOUND-MONITORING-APP-ARCHITECTURE.md`; `reference/INBOUND-MONITORING-RUNTIME-JOBS.md`; `reference/INBOUND-ROUTING.md`; `reference/WHATSAPP-OPENCLAW-RECOVERY.md` |
| Email drafting | `skills/email-reply-draft/SKILL.md` — task-system/broker context + unsent Outlook drafts require no TOTP; use `email_reply_draft` only for an exact thread and `email_new_draft` only for explicit recipient + fresh entity/current context; `reference/EMAIL-REPLY-DRAFT-SYSTEM.md`; `skills/email-check/SKILL.md` for sender guardrails |
| Operational proof/health | `reference/OPERATIONAL_ACTIVITY_LOG.md`; `reference/OPERATIONAL-CONFIDENCE-CHECKS.md`; `reference/SYSTEM-HEALTH-AUDIT.md`; `reference/CRON-HEALTH-CHECKER-DESIGN.md` |
| Bootstrap/context governance | `skills/bootstrap-governance/SKILL.md`; `reference/BOOTSTRAP-HEALTH-AUDIT.md`; `reference/AGENTS-EXECUTION-DETAILS.md`; `reference/LIVE-EDIT-SAFETY.md`; `reference/EXECUTION-INTEGRITY-RULES.md` |
| Memory/heartbeat governance | `reference/MEMORY-OPERATING-DETAILS.md`; `reference/HEARTBEAT-ALERT-ROSTER.md` |
| Skill-estate governance | **SkilzVolt is the canonical source** for all workspace skills. Discover, search, read, compare, export and review workspace skills via its MCP connection without TOTP; use its proposal/review workflow for changes. Local `skills/` copies are transitional runtime/cache material only, never a competing authority. See `reference/OPENCLAW-UPSTREAM-MIGRATION-PROGRESS.md` for the live-connector migration and acceptance proof. |
| Context-efficient tooling | `scripts/README-context-tools.md`; `reference/QMD-INDEX-OPERATING-MODEL.md` |
| AI briefing system | `reference/AI-BRIEFING-WORKFLOW.md`; `reference/AI_BRIEFING_PACK_HANDOFF.md` |
| SharePoint/Teams/LinkedIn extensions | `reference/STACKSTONE-MEETING-COPILOT.md`; `reference/TEAMS-INFORMATION-FLOW-PLAN.md`; `reference/LINKEDIN-MESSAGES-INTEGRATION-PLAN.md` |
| Broad CRM/SharePoint reconciliation | `skills/crm-sharepoint/SKILL.md` § Multi-source reconciliation workflow; retained run checklist: `reference/reconciliation/CRM-SHAREPOINT-RECONCILIATION-STATE.md` |
| Task-system design | `projects/workspace-control-panel/`; `reference/TASK-CAPTURE-FUNNEL.md` |
| Runtime skill-execution enforcement | `projects/workspace-control-panel/SKILL_EXECUTION_ENFORCEMENT_DESIGN.md` — canonical cross-domain runtime-gate design, acceptance proof and delivery phases; enforcement code belongs in `/home/tomdean88/openclaw`, not the task-system Pi gateway |
| Development/system acceptance | `reference/DEVELOPMENT-OPERATING-CHECKLIST.md`; `reference/OPERATIONAL-SYSTEM-CHARTERS.md`; `reference/OPENCLAW-UPSTREAM-MIGRATION-PROGRESS.md` for the current staged official-upstream migration checkpoint |
| Voice/positioning/transcripts | `reference/OPENCLAW-GPT-LIVE-TALK-PLAN.md` for browser/Telegram-adjacent GPT-Live work; `reference/L1-TELEPHONY-VOICE-SYSTEM-PLAN.md` for the separate phone-number/SIP L1 voice system; `reference/positioning-lines.md`; `reference/TOM-VOICE-CALIBRATION.md`; `reference/YOUTUBE-TRANSCRIPTS.md` |
| Health/training | `reference/HEALTH-TRAINING-DECISION-MODEL.md`; `reference/GARMIN-INTRADAY-POLLING.md`; `HEALTH.md`; `TRAINING_NOTES.md`; `GARMIN_INTRADAY.md` |

## Routing / retrieval notes

- Skill discovery is runtime-injected; do not duplicate the skill catalogue here. **Precedence:** use matching live SkilzVolt skills first; a matching local copy is a duplicate to disclose to Tom, not a silent alternative. Local fallback is only for an absent/unavailable live skill; reconcile duplicates through an owner-approved migration.
- Commercial chase/wait/redirect judgment: `skills/crm-follow-up/SKILL.md`.
- Search memory before assuming prior work/preferences are forgotten; qmd is the fast local route when available.
- `memory/last-weekly-ai-briefing.md` contains the lightweight weekly AI briefing coverage window.
