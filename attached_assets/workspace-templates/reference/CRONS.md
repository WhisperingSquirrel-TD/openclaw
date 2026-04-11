# CRONS.md — All Cron Jobs

_Reference file. Updated by install script. Do not edit manually._

## Schedule

| Time | Script | Log |
|---|---|---|
| 04:00 daily | `~/.openclaw/integrations/provider-switch/daily-reset.py` | `~/.openclaw/integrations/provider-switch/daily-reset.log` |
| 06:55 daily | `~/.openclaw/integrations/health/health_check.py` | `~/.openclaw/workspace/memory/health-check-log.txt` |
| 08:00 daily | `~/.openclaw/integrations/crm/poll-crm.py` | `~/.openclaw/workspace/memory/poll-crm-log.txt` |
| 09:00 daily | `~/.openclaw/integrations/garmin/poll-garmin.py` | `~/.openclaw/workspace/memory/poll-garmin-log.txt` |
| Every 1 min | `~/.openclaw/integrations/microsoft/sharepoint_queue_processor.py` | `~/.openclaw/integrations/microsoft/sharepoint-queue.log` |
| Every 2 min | `~/.openclaw/integrations/stackstone/enquiry_poller.py` | `~/.openclaw/integrations/stackstone/enquiry-poller.log` |
| Every 5 min | `~/.openclaw/integrations/stackstone/report_poller.py` | `~/.openclaw/integrations/stackstone/poller.log` |
| Every 15 min | `~/.openclaw/integrations/microsoft/sharepoint_cache_poller.py` | `~/.openclaw/integrations/microsoft/sharepoint-cache.log` |

## Notes
- Never schedule anything at 06:xx (reserved for prospector/CRM) or 07:xx (another job)
- Garmin runs at 09:00 — if session expired, run interactively: `python3 ~/.openclaw/integrations/garmin/poll-garmin.py`
- Health check at 06:55 writes SYSTEM_HEALTH.md if any issues found
- Provider reset runs at 04:00 — resets to openai-codex/gpt-5.4

## Checking cron health
```bash
crontab -l
tail -50 ~/.openclaw/workspace/memory/poll-garmin-log.txt
tail -50 ~/.openclaw/integrations/stackstone/enquiry-poller.log
```
