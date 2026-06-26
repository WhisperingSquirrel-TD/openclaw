# Pi File Locations, Logs & Diagnostics Reference

> Part of the OpenClaw knowledge base. Map: [`../replit.md`](../replit.md).
> Related: [Pi deployment](./pi-deployment.md) · [Troubleshooting](./troubleshooting.md) · integration runbooks under [`./integrations/`](./integrations/)

This is the consolidated map of where things live on the Pi and how to debug them.

## Email integration files

| File                                                      | Purpose                                                                                   |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `~/.openclaw/integrations/known-contacts.txt`             | Shared trusted contacts list — read by all pollers. One email per line.                   |
| `~/.openclaw/integrations/microsoft/poll.py`              | Microsoft Graph email poller — parameterised, serves both personal and assistant accounts |
| `~/.openclaw/integrations/microsoft/token-microsoft.json` | Personal Microsoft OAuth token (tom@stackstoneconsulting.co.uk)                           |
| `~/.openclaw/integrations/microsoft/token-assistant.json` | **Canonical** assistant account OAuth token (assistant@stackstoneconsulting.co.uk) — used by SharePoint, send.py, email + calendar pollers. See [microsoft.md](./integrations/microsoft.md#microsoft-oauth--unified-scope-strategy-important) |
| `~/.openclaw/integrations/microsoft-l1/token.json`        | Legacy assistant token path (older setups) — prefer `token-assistant.json` above          |
| `~/.openclaw/integrations/google/gmail_poll.py`           | Gmail email poller script                                                                 |
| `~/.openclaw/integrations/google/gmail-credentials.json`  | Gmail OAuth app credentials (from Google Cloud Console)                                   |
| `~/.openclaw/integrations/google/gmail-token.json`        | Gmail OAuth token (delete and re-run poller to re-auth)                                   |

See [Integrations: Microsoft](./integrations/microsoft.md) and [Google](./integrations/google.md) for auth details.

### Feed files (read by L1 directly via `cat` — no TOTP needed)

| File                                          | Purpose                                                |
| --------------------------------------------- | ------------------------------------------------------ |
| `~/.openclaw/workspace/MICROSOFT_INBOX.md`    | Personal Microsoft trusted inbox (tom@)                |
| `~/.openclaw/workspace/MICROSOFT_EXTERNAL.md` | Personal Microsoft external/unknown senders            |
| `~/.openclaw/workspace/ASSISTANT_INBOX.md`    | Assistant inbox (assistant@stackstoneconsulting.co.uk) |
| `~/.openclaw/workspace/ASSISTANT_EXTERNAL.md` | Assistant external/unknown senders                     |
| `~/.openclaw/workspace/GMAIL_INBOX.md`        | Trusted Gmail inbox summary                            |
| `~/.openclaw/workspace/GMAIL_EXTERNAL.md`     | External/unknown Gmail inbox                           |

### Poll logs (debug here first when feeds go stale)

| File                                                  | Purpose                                           |
| ----------------------------------------------------- | ------------------------------------------------- |
| `~/.openclaw/workspace/memory/poll-microsoft-log.txt` | Personal Microsoft poller — check for auth errors |
| `~/.openclaw/workspace/memory/poll-assistant-log.txt` | Assistant poller — check for auth errors          |
| `~/.openclaw/workspace/memory/poll-gmail-log.txt`     | Gmail poller — check for `invalid_grant`          |

## Security & config files

| File                                     | Purpose                                                                   |
| ---------------------------------------- | ------------------------------------------------------------------------- |
| `~/.openclaw/openclaw.json`              | Main gateway config (locked with `chattr +i`)                             |
| `~/.openclaw/audit/outbound-audit.jsonl` | Append-only outbound message audit log                                    |
| `~/.openclaw/totp/totp-secret.enc`       | Encrypted TOTP secret (locked with `chattr +i`)                           |
| `/mnt/l1-secure/SOUL.md`                 | L1 personality and context file — edit with `nano /mnt/l1-secure/SOUL.md` |
| `~/l1-hashes.txt`                        | SHA-256 integrity hashes of secure files — regenerated on every install   |

See [Security](./security.md) and [TOTP](./totp.md).

## All log files — always use these, journald does NOT work for user services on this Pi

| What                        | Log path                                                                          |
| --------------------------- | --------------------------------------------------------------------------------- |
| **Gateway (L1)**            | `~/.openclaw/gateway.log`                                                         |
| Daily model reset           | `~/.openclaw/workspace/memory/daily-reset.log`                                    |
| Garmin poller               | `~/.openclaw/workspace/memory/poll-garmin-log.txt`                                |
| CRM poller                  | `~/.openclaw/workspace/memory/poll-crm-log.txt`                                   |
| SharePoint cache poller     | `~/.openclaw/integrations/microsoft/sp-cache-poller.log`                          |
| SharePoint queue processor  | `~/.openclaw/integrations/microsoft/sp-queue-processor.log`                       |
| SharePoint housekeeping     | `~/.openclaw/integrations/microsoft/sp-housekeeping.log`                          |
| Stackstone report poller    | `~/.openclaw/integrations/stackstone/poller.log`                                  |
| Stackstone enquiry poller   | `~/.openclaw/integrations/stackstone/enquiry-poller.log`                          |
| YouTube channel poller      | `~/.openclaw/integrations/youtube/channel-poller.log`                             |
| AI briefing pipeline        | `~/.openclaw/integrations/ai-briefing/pipeline.log`                               |
| Health check                | `~/.openclaw/integrations/health/health-check.log`                                |
| Stackstone poll (cron)      | `/tmp/l1-stackstone-poll.log`                                                     |

**Live tail of gateway** (watch what happens when you send L1 a message in Telegram):
```bash
tail -f ~/.openclaw/gateway.log
```

## Key paths

| What                            | Path                                                                |
| ------------------------------- | ------------------------------------------------------------------- |
| Main config (locked)            | `~/.openclaw/openclaw.json`                                         |
| API keys / secrets              | `~/.openclaw/.env`                                                  |
| System skills (10 core)         | `~/.openclaw/skills/`                                               |
| Workspace skills (32 custom)    | `~/.openclaw/workspace/skills/`                                     |
| L1 memory files                 | `~/.openclaw/workspace/memory/`                                     |
| Session transcripts             | `~/.openclaw/agents/main/sessions/`                                 |
| All integrations                | `~/.openclaw/integrations/`                                         |
| Microsoft tokens                | `~/.openclaw/integrations/microsoft/token-*.json`                   |
| Google OAuth tokens             | `~/.openclaw/oauth/google/`                                         |
| Daily reset script              | `~/.openclaw/integrations/provider-switch/daily-reset.py`           |
| SharePoint manifest/cache       | `~/.openclaw/integrations/microsoft/sharepoint-manifest.json`       |
| SharePoint write queue          | `~/.openclaw/integrations/microsoft/sharepoint-queue.json`          |

See [Skills path configuration](./integrations/skills.md) for the `skills.paths` requirement.

## Systemd user services on this Pi

| Service                              | Purpose                          |
| ------------------------------------ | -------------------------------- |
| `openclaw-gateway.service`           | Main L1 gateway                  |
| `openclaw-mgmt-bot.service`          | Telegram management bot          |
| `openclaw-email-assistant.service`   | Email assistant channel          |
| `openclaw-email-gmail.service`       | Gmail poller                     |
| `openclaw-email-microsoft.service`   | Microsoft mail poller            |
| `openclaw-calendar-google.service`   | Google Calendar poller           |
| `openclaw-calendar-microsoft.service`| Microsoft Calendar poller        |

**Commands:**
```bash
systemctl --user status openclaw-gateway.service
systemctl --user restart openclaw-gateway.service
systemctl --user start openclaw-gateway.service
systemctl --user stop openclaw-gateway.service
```

See [Pi deployment: background services](./pi-deployment.md#background-services-pi) for why these are systemd user services (and `enable-linger`).

## First-check diagnostics — run these when L1 is silent or stuck

```bash
# 1. Is the gateway actually running?
systemctl --user status openclaw-gateway.service

# 2. What's in the gateway log right now?
tail -30 ~/.openclaw/gateway.log

# 3. Is the config valid JSON?
python3 -c "import json; json.load(open('/home/tomdean88/.openclaw/openclaw.json')); print('JSON OK')"

# 4. What model is L1 using?
python3 -c "import json; cfg=json.load(open('/home/tomdean88/.openclaw/openclaw.json')); print(cfg.get('agents',{}).get('defaults',{}).get('model',{}))"

# ⚠️  NEVER set agent model like this — introduces legacy key that crashes gateway:
#   cfg.setdefault('agent', {})['model'] = 'openai/gpt-5.4'   ← WRONG (old schema)
#
# ALWAYS use this form:
#   cfg.setdefault('agents',{}).setdefault('defaults',{}).setdefault('model',{})['primary'] = 'openai/gpt-5.4'

# 5. Check for rate limit / compaction error
grep -i "usage limit\|compaction\|summarization failed" ~/.openclaw/gateway.log | tail -5

# 6. Check all errors in gateway log
grep -i "error\|warn\|fail" ~/.openclaw/gateway.log | tail -20
```

For deeper failure patterns (model routing, auth, crash-loops) see [Troubleshooting](./troubleshooting.md).

## Config editing (locked file)

```bash
sudo chattr -i ~/.openclaw/openclaw.json   # unlock
# ... edit ...
sudo chattr +i ~/.openclaw/openclaw.json   # re-lock
systemctl --user restart openclaw-gateway.service
```

**Always validate JSON before restarting:**
```bash
python3 -c "import json; json.load(open('/home/tomdean88/.openclaw/openclaw.json')); print('OK')"
```
