# Trusted Email Reader

TOTP-free email body reader for approved senders only.

## Purpose

Read full email bodies and download attachments from Microsoft Graph API without requiring exec/TOTP gates, but ONLY for emails from known/trusted contacts.

## Security Model

- Checks sender against `~/.openclaw/integrations/known-contacts.txt`
- Refuses to read emails from non-approved senders (exit code 1)
- Uses existing Microsoft token files (no new auth needed)

## Usage

### Microsoft / Outlook basic read

```bash
python3 read_email.py <message_id> --account assistant
```

### Microsoft / Outlook with attachment download

```bash
python3 read_email.py <message_id> --account assistant --download-attachments
```

### Gmail basic read

```bash
python3 read_gmail.py <gmail_message_id>
```

### Gmail with attachment download

```bash
python3 read_gmail.py <gmail_message_id> --download-attachments
```

### Custom attachment directory

```bash
python3 read_email.py <message_id> --account assistant \
  --download-attachments \
  --output-dir /path/to/attachments
```

## Exit Codes

- `0` = Success
- `1` = Sender not approved (security boundary)
- `2` = Error (token missing, API failure, etc.)

## Output Format

JSON to stdout:

```json
{
  "success": true,
  "message_id": "AAMk...",
  "subject": "Your receipt from Anthropic...",
  "from": {
    "name": "Anthropic, PBC",
    "address": "invoice+statements@mail.anthropic.com"
  },
  "received": "2026-06-07T15:16:00Z",
  "body": {
    "content": "...",
    "type": "html"
  },
  "has_attachments": true,
  "attachments": [
    {
      "name": "invoice.pdf",
      "contentType": "application/pdf",
      "size": 45678
    }
  ],
  "downloaded_files": [
    "/home/tomdean88/.openclaw/workspace/expense-attachments/AAMk.../invoice.pdf"
  ]
}
```

## Integration with OpenClaw

Call directly from Python (no exec gate):

```python
import subprocess
import json

result = subprocess.run([
    'python3',
    '/home/tomdean88/pi-services/trusted-email-reader/read_email.py',
    message_id,
    '--account', 'assistant',
    '--download-attachments'
], capture_output=True, text=True)

if result.returncode == 0:
    email_data = json.loads(result.stdout)
    # Process email_data
elif result.returncode == 1:
    # Sender not approved - security boundary
    pass
else:
    # Error
    pass
```

## Token Files

Uses existing tokens from:

- `~/.openclaw/integrations/microsoft/token-assistant.json`
- `~/.openclaw/integrations/microsoft/token-microsoft.json`

## Approved Senders

Reads from:

- `~/.openclaw/integrations/known-contacts.txt`

Add new approved senders there (one email per line).
