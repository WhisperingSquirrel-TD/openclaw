# Replit prompt — OpenClaw fork changes for Stackstone networking report system
# Use this in Replit against the WhisperingSquirrel-TD/openclaw fork.
# Do not rebuild from scratch — extend only what is described below.

---

## Context

This is a personal AI assistant (L1 / Lobstromonous1) running on a Raspberry Pi 4
via a forked version of OpenClaw. It has an existing Microsoft Graph integration
for reading email and calendar. Email *sending* by L1 itself is gated behind a
TOTP queue (pending actions written to file, require Tom's TOTP code to execute).

I want to add a new, separate HTTP endpoint — `/send-report` — to the OpenClaw
server process. This endpoint is NOT part of L1's decision-making. It is called
directly by an external trusted system (the Stackstone website) and sends a
single pre-formed email via MS Graph. It bypasses the TOTP queue entirely because
the website — not L1 — is deciding to send it. L1 is just the mail relay.

---

## What to add

### 1. New HTTP endpoint: POST /send-report

Add this route to OpenClaw's existing HTTP server (wherever the gateway's API
routes are registered — likely in `src/gateway/` or `src/server/`).

The endpoint must:

**Authentication**
- Read a secret from env var `REPORT_SEND_SECRET`
- Expect header: `Authorization: Bearer <REPORT_SEND_SECRET>`
- Reject with 401 if missing or wrong
- Log the rejection with the source IP but do not expose the secret

**Rate limiting**
- Maintain a simple in-memory rolling counter: max `REPORT_MAX_PER_DAY` sends
  in any 24-hour window (default 30 if env var not set)
- Reject with 429 if limit exceeded, include `{ remaining: 0, resetAt: <ISO> }`
- Persist the counter to `~/.openclaw/workspace/report_send_log.json` on each
  send so it survives a gateway restart

**Payload — accept JSON:**
```json
{
  "to": {
    "email": "sarah@acmeltd.co.uk",
    "name": "Sarah Jones"
  },
  "reportUrl": "https://stackstoneconsulting.co.uk/report/uuid-here",
  "companyName": "Acme Ltd",
  "firstName": "Sarah"
}
```

**Validation — reject with 400 if:**
- `to.email` missing or not a valid email format
- `to.name` missing or empty
- `reportUrl` missing or does not start with `https://stackstoneconsulting.co.uk`
  (hard-coded domain check — this endpoint only ever sends Stackstone report links)
- `companyName` missing or empty
- `firstName` missing or empty

**On valid request:**
- Respond 202 immediately: `{ status: "accepted" }`
- Send the email asynchronously (do not await before responding)

**Email send — use the existing Graph integration:**
- Find where OpenClaw currently calls the Microsoft Graph `sendMail` endpoint
  for L1's outbound email. Use the same token source, the same token refresh
  logic, and the same Graph client. Do not create a new auth flow.
- Send from the address stored in env var `SENDER_EMAIL`
  (default: process.env.SENDER_EMAIL)
- The email content is fixed — build it from the payload using the template below

**Email template:**

Subject: `Your AI Opportunity Report — {companyName}`

Body (HTML):
```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{margin:0;padding:0;background:#F0EEE9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}
  .wrap{max-width:580px;margin:32px auto;background:#fff;border-radius:8px;overflow:hidden}
  .top{background:#2C2C2E;padding:24px 32px 0}
  .logo-row{display:flex;align-items:center;gap:10px;margin-bottom:20px}
  .logo-name{color:#fff;font-size:17px;font-weight:700;letter-spacing:-0.3px}
  .rule{height:3px;background:#D4A017}
  .hero{background:#48484A;padding:24px 32px}
  .hero h1{color:#fff;font-size:20px;font-weight:700;margin:0 0 8px}
  .hero p{color:rgba(255,255,255,0.6);font-size:14px;margin:0;line-height:1.6}
  .body{padding:32px}
  .body p{font-size:15px;color:#3C3C3E;line-height:1.7;margin:0 0 16px}
  .cta-wrap{margin:24px 0 0}
  .cta-btn{display:inline-block;background:#D4A017;color:#2C2C2E;text-decoration:none;padding:14px 28px;border-radius:6px;font-size:15px;font-weight:700}
  .note{font-size:12px;color:#AEAEB2;margin-top:16px !important}
  .footer{background:#F0EEE9;padding:20px 32px;border-top:1px solid #E0DDD6}
  .footer p{font-size:12px;color:#8E8E93;margin:0 0 3px;line-height:1.5}
  .footer a{color:#8E8E93}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div class="logo-row">
      <svg width="26" height="26" viewBox="0 0 36 36" fill="none">
        <rect x="10" y="24" width="16" height="5" rx="2" fill="#D4A017"/>
        <rect x="7" y="18" width="22" height="5" rx="2" fill="#787878"/>
        <rect x="12" y="12" width="12" height="5" rx="2" fill="#A0A0A0"/>
        <rect x="15" y="6" width="6" height="5" rx="2" fill="#C0C0C0"/>
      </svg>
      <span class="logo-name">Stackstone Consulting</span>
    </div>
  </div>
  <div class="rule"></div>
  <div class="hero">
    <h1>Hi {firstName},</h1>
    <p>Great to meet you. Your bespoke AI opportunity report for {companyName} is ready.</p>
  </div>
  <div class="body">
    <p>I have put together a report based on research into {companyName} — covering where AI can make the biggest practical difference for a business in your position, with realistic timelines and no fluff.</p>
    <p>It includes your sector context, a primary opportunity specific to you, three quick wins you could act on in the next 90 days, and honest caveats about what to watch out for.</p>
    <div class="cta-wrap">
      <a href="{reportUrl}" class="cta-btn">View your report</a>
    </div>
    <p class="note">The report has a PDF download button if you would like to save or share it internally. The link does not expire.</p>
  </div>
  <div class="footer">
    <p><strong>{senderName}</strong> — Founder, Stackstone Consulting</p>
    <p><a href="mailto:{senderEmail}">{senderEmail}</a> &nbsp;|&nbsp; <a href="https://stackstoneconsulting.co.uk">stackstoneconsulting.co.uk</a></p>
    <p>Abingdon, Oxfordshire</p>
  </div>
</div>
</body>
</html>
```

Replace `{firstName}`, `{companyName}`, `{reportUrl}`, `{senderName}`, `{senderEmail}`
with the payload values and env var values respectively.
`{senderName}` = env var `SENDER_NAME` (default: "Tom Dean")
`{senderEmail}` = env var `SENDER_EMAIL`

**After a successful Graph send:**
- Append a line to `~/.openclaw/workspace/report_send_log.json` with:
  `{ "ts": "<ISO>", "to": "<email>", "company": "<companyName>" }`
- Send a Telegram message to Tom's chat ID (read from existing OpenClaw config,
  same place L1 sends Telegram notifications now) with text:
  `[Stackstone] Report sent to {firstName} {lastName} ({companyName}) — {reportUrl}`

**On Graph send failure:**
- Log the error with full detail
- Send a Telegram notification: `[Stackstone] FAILED to send report to {to.name} ({companyName}): {error message}`
- Do not retry automatically

---

### 2. New env vars to add to openclaw.json or .env

```
REPORT_SEND_SECRET      string   shared secret with the Stackstone website
REPORT_MAX_PER_DAY      number   max sends per 24h rolling window (default 30)
SENDER_EMAIL            string   tom@stackstoneconsulting.co.uk
SENDER_NAME             string   Tom Dean
```

If `SENDER_EMAIL` and `SENDER_NAME` are already present in the OpenClaw config
for L1's existing email flow, reuse them — do not duplicate.

---

### 3. Health check addition

Add `/send-report/health` (GET, no auth) that returns:

```json
{
  "status": "ok",
  "sentToday": 4,
  "remainingToday": 26,
  "resetAt": "<ISO timestamp of when the 24h window resets>"
}
```

---

### 4. What NOT to change

- Do not touch L1's TOTP flow or queue file pattern in any way
- Do not touch `pending_bounces.txt`, `pending_unsubs.txt`, or any existing
  queue files
- Do not change any existing Graph auth or token refresh logic — only reuse it
- Do not change SOUL.md or any workspace files
- Do not add any new npm dependencies if the existing codebase already has an
  HTTP server and a fetch/axios equivalent available
- Do not add a UI or admin panel

---

### 5. After making the changes

Provide:
1. A summary of which files were changed and what was added to each
2. The exact deploy commands to pull the changes to the Pi and restart the gateway
3. A test curl command I can run from my laptop to verify the endpoint is working
   (using a placeholder secret and a test payload)
4. Confirmation of which port the endpoint runs on (same port as the existing
   OpenClaw gateway)
