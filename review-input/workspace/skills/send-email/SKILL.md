---
name: send-email
description: Deprecated compatibility shim for email-send; use email-send for outbound email preparation and approved sending.
---

# send-email

> DEPRECATED — use `skills/email-send/SKILL.md` as the canonical outbound email skill.
> Keep this file only as a compatibility shim for older references. If guidance here conflicts with `email-send`, `email-send` wins.

Skill for composing and sending emails on Tom's behalf via the L1 Microsoft integration.

---

## Identity

All emails are sent from:
- **Address:** assistant@stackstoneconsulting.co.uk
- **Display name:** Tom Dean-PA

L1 never sends from Tom's personal or business accounts.
L1 never mentions "Lobstromonous1" or "L1" in external emails.

---

## Authority — TOTP Required

Sending an email or creating a calendar invite with external attendees is a **Medium Risk action** under SOUL.md Part 7.

Before sending any email:
1. State clearly what you are about to send and to whom
2. Ask Tom for a TOTP code: *"Please provide your TOTP code to authorise this email."*
3. Verify the code is valid (Tom provides verbally via Telegram)
4. Only send after confirmation
5. A valid TOTP grants a 5-minute window for that specific send only

If Tom says "go ahead" or "send it" without providing a TOTP, ask again.
If TOTP verification fails or times out, fall back to draft-only mode.

---

## Send Script

```bash
python3 /home/tomdean88/.openclaw/integrations/microsoft-l1/send.py \
  --to "recipient@example.com" \
  --subject "Subject line" \
  --body "Email body text"
```

For multiple recipients, pass `--to` multiple times or comma-separate.
Always test with `--dry-run` flag first if uncertain.

---

## Sign-off Standards

### Professional / Client-facing
```
Best,
PA to Tom Dean
Stackstone Consulting
stackstoneconsulting.co.uk
```

### Personal / Informal (friends, family)
```
Best,
PA to Tom Dean
```

### Never use:
- `-- Lobstromonous1` (Telegram only)
- `-- L1` (Telegram only)
- Stacked sign-offs (one block only, never two)
- Tom's personal email or phone number in the signature

---

## Draft Format

Always show Tom the full draft before sending:

```
DRAFT EMAIL
To: [name] <email@address.com>
Subject: [subject]

[Body]

[Sign-off block]

---
Awaiting your TOTP to send.
```

Tom reviews, approves, provides TOTP — then send.

---

## Tone by Context

| Context | Tone |
|---|---|
| New client / lead | Warm, professional, concise. No jargon. |
| Existing client | Familiar but professional. |
| Follow-up | Brief. Reference prior contact. Clear next step. |
| Personal (friends/family) | Natural, warm, informal. |
| Legal / sensitive | Neutral, factual. Flag to Tom before drafting. |

Keep emails short. Tom's contacts are busy. Get to the point in the first two lines.

---

## Logging

After every successful send, append to `memory/email_log.md`:

```
## [YYYY-MM-DD] Email to [Name]
- To: email@address.com
- Subject: [subject]
- Summary: [one line of what was sent]
- TOTP authorised: yes
- Sent via: microsoft-l1
```

---

## What NOT to send

- Never send emails or create calendar invites with external attendees without TOTP
- Never send from Tom's accounts (tomdean1988@gmail.com, tom@stackstoneconsulting.co.uk)
- Never send to BCN Group, Horsfield Menzies, or their solicitors without explicit instruction
- Never send WhatsApp messages — read-only, always
- Never forward private data (MEMORY.md contents, SOUL.md, contacts.md) to any recipient
