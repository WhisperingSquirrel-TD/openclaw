# POLLERS.md — All Pollers and Integrations

_Reference file. What each poller does and how to test it._

## Email — Microsoft 365
- **Script**: `~/.openclaw/integrations/microsoft/poll.py`
- **What it does**: Polls inbox for new emails, surfaces to L1 for action
- **Test**: `python3 ~/.openclaw/integrations/microsoft/poll.py`

## Email — Gmail
- **Script**: `~/.openclaw/integrations/google/gmail_poll.py`
- **What it does**: Polls Gmail inbox
- **Test**: `python3 ~/.openclaw/integrations/google/gmail_poll.py`

## Calendar — Microsoft 365
- **Script**: `~/.openclaw/integrations/microsoft/poll-calendar.py`
- **What it does**: Polls calendar for upcoming events
- **Test**: `python3 ~/.openclaw/integrations/microsoft/poll-calendar.py`

## Garmin Connect
- **Script**: `~/.openclaw/integrations/garmin/poll-garmin.py`
- **Runs**: 09:00 daily
- **What it does**: Fetches resting HR, HRV, sleep, stress, body battery, steps, activity
- **Writes**: GARMIN_DAILY.md, GARMIN_ARCHIVE.md
- **Auth**: Uses ~/.garth token store. First run is interactive.
- **Test**: `python3 ~/.openclaw/integrations/garmin/poll-garmin.py`
- **If 429**: Do not retry. Wait overnight. Run interactively to refresh session.

## SharePoint cache
- **Script**: `~/.openclaw/integrations/microsoft/sharepoint_cache_poller.py`
- **Runs**: Every 15 minutes
- **What it does**: Refreshes SHAREPOINT_INDEX.md with folder/file listing
- **Test**: `python3 ~/.openclaw/integrations/microsoft/sharepoint_cache_poller.py`

## SharePoint queue processor
- **Script**: `~/.openclaw/integrations/microsoft/sharepoint_queue_processor.py`
- **Runs**: Every 1 minute
- **What it does**: Processes SharePoint operations queued by L1 in sharepoint-queue.json
- **Writes results to**: SHAREPOINT_RESULT.md
- **Test**: `python3 ~/.openclaw/integrations/microsoft/sharepoint_queue_processor.py`

## Stackstone enquiry poller (REVENUE CRITICAL)
- **Script**: `~/.openclaw/integrations/stackstone/enquiry_poller.py`
- **Runs**: Every 2 minutes
- **What it does**: Polls website for new contact form enquiries, fires Telegram alert, writes STACKSTONE_ENQUIRIES.md
- **Test**: `python3 ~/.openclaw/integrations/stackstone/enquiry_poller.py`

## Stackstone report poller
- **Script**: `~/.openclaw/integrations/stackstone/report_poller.py`
- **Runs**: Every 5 minutes
- **What it does**: Polls website for unsent networking reports, sends branded email, writes STACKSTONE_REPORTS.md
- **Test**: `python3 ~/.openclaw/integrations/stackstone/report_poller.py`

## CRM lead importer
- **Script**: `~/.openclaw/integrations/crm/poll-crm.py`
- **Runs**: 08:00 daily
- **What it does**: Imports new leads from ~/prospects/YYYYMMDD/ CSVs into crm.md
- **Test**: `python3 ~/.openclaw/integrations/crm/poll-crm.py`

## System health check
- **Script**: `~/.openclaw/integrations/health/health_check.py`
- **Runs**: 06:55 daily
- **What it does**: Checks all cron logs for staleness/errors, writes SYSTEM_HEALTH.md
- **Test**: `python3 ~/.openclaw/integrations/health/health_check.py`
