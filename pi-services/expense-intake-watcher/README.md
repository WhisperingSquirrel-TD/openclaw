# Expense Intake Watcher

Pi-native watcher that scans trusted inbox mirrors for new expense-shaped emails and logs them automatically.

## Purpose

Turn mirrored inbox updates into actual expense capture behavior.

## Inputs

- `/home/tomdean88/.openclaw/workspace/GMAIL_INBOX.md`
- `/home/tomdean88/.openclaw/workspace/ASSISTANT_INBOX.md`
- `/home/tomdean88/.openclaw/workspace/MICROSOFT_INBOX.md`

## Readers used

- Microsoft: `/home/tomdean88/pi-services/trusted-email-reader/read_email.py`
- Gmail: `/home/tomdean88/pi-services/trusted-email-reader/read_gmail.py`

## State

- Runtime state lives outside the repo at `~/.openclaw/runtime/expense-intake-watcher/state.json`
- Runtime log lives outside the repo at `~/.openclaw/runtime/expense-intake-watcher/watcher.log`

## Current scope

- Detect new expense-shaped emails
- Read full body through the trusted reader route
- Skip duplicates already present in `seer-expenses.md`
- Insert new expense rows into the Software & Subscriptions section
- Download attachments where the reader supports it

## Known limits

- SharePoint artifact queueing is not yet wired here
- Vendor parsing currently tuned for Anthropic / OpenAI / Replit / Microsoft
- The watcher is only as good as the inbox mirrors + trusted readers
