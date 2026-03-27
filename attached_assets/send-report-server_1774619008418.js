/**
 * Stackstone — L1 /send-report endpoint
 * Raspberry Pi addition, runs alongside L1.
 *
 * Called exclusively by stackstoneconsulting.co.uk after it has generated
 * and stored a report. This endpoint's only job is to send one email via
 * MS Graph. It never touches L1's TOTP queue or general email flow.
 *
 * Security model:
 *   - Shared secret between site and Pi (INTAKE_SITE_SECRET)
 *   - Rate limited to MAX_PER_DAY sends per 24h rolling window
 *   - Only sends to the exact recipient passed — no free-form content
 *   - Separate from all other L1 email flows
 *
 * Add to your Pi's process manager or run alongside L1:
 *   node send-report-server.js
 *
 * Required env vars (add to your existing Pi .env):
 *   INTAKE_SITE_SECRET   — shared secret, set same in Replit secrets
 *   MS_GRAPH_TOKEN       — valid Graph token with Mail.Send scope
 *   SENDER_EMAIL         — tom@stackstoneconsulting.co.uk
 *   SENDER_NAME          — Tom Dean
 *   REPORT_PORT          — port for this server (default: 5051, keep separate from L1)
 *   MAX_PER_DAY          — max emails per 24h rolling window (default: 30)
 *
 * Optional:
 *   TELEGRAM_CHAT_ID     — your chat ID for confirmations
 *   TELEGRAM_BOT_TOKEN   — bot token
 */

'use strict';

const express = require('express');

const app     = express();
const PORT    = process.env.REPORT_PORT || 5051;
const SECRET  = process.env.INTAKE_SITE_SECRET;
const MAX_PER_DAY = parseInt(process.env.MAX_PER_DAY || '30', 10);

['INTAKE_SITE_SECRET', 'MS_GRAPH_TOKEN', 'SENDER_EMAIL'].forEach(k => {
  if (!process.env[k]) throw new Error(`Missing required env var: ${k}`);
});

app.use(express.json({ limit: '8kb' }));

app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS, GET');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});

// ── Rate limiting ─────────────────────────────────────────────────────────────

const sendLog = []; // { ts: Date }

function rateLimitOk() {
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  // Remove entries older than 24h
  while (sendLog.length && sendLog[0].ts < cutoff) sendLog.shift();
  return sendLog.length < MAX_PER_DAY;
}

function recordSend() {
  sendLog.push({ ts: Date.now() });
}

// ── Auth ──────────────────────────────────────────────────────────────────────

function requireSecret(req, res, next) {
  const token = (req.headers.authorization || '').replace(/^Bearer\s+/i, '');
  if (token !== SECRET) {
    console.warn(`[send-report] unauthorised attempt from ${req.ip}`);
    return res.status(401).json({ error: 'Unauthorised' });
  }
  next();
}

// ── Payload validation ────────────────────────────────────────────────────────

function validatePayload(body) {
  if (!body.to?.email || !body.to?.name)   return 'Missing to.email or to.name';
  if (!body.reportUrl)                      return 'Missing reportUrl';
  if (!body.companyName)                    return 'Missing companyName';
  if (!body.firstName)                      return 'Missing firstName';
  if (!/^https?:\/\/.+/.test(body.reportUrl)) return 'reportUrl must be a full URL';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.to.email)) return 'Invalid recipient email';
  return null;
}

// ── MS Graph send ─────────────────────────────────────────────────────────────

async function sendViaGraph(payload) {
  const { to, reportUrl, companyName, firstName } = payload;
  const senderEmail = process.env.SENDER_EMAIL;
  const senderName  = process.env.SENDER_NAME || 'Tom Dean';

  const emailBody = buildEmailHtml(firstName, companyName, reportUrl, senderEmail, senderName);

  const message = {
    subject: `Your AI Opportunity Report — ${companyName}`,
    body: { contentType: 'HTML', content: emailBody },
    toRecipients: [{ emailAddress: { address: to.email, name: to.name } }],
    replyTo: [{ emailAddress: { address: senderEmail, name: senderName } }]
  };

  const resp = await fetch('https://graph.microsoft.com/v1.0/me/sendMail', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${process.env.MS_GRAPH_TOKEN}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ message, saveToSentItems: true })
  });

  if (!resp.ok) {
    const detail = await resp.text().catch(() => '');
    throw new Error(`Graph sendMail ${resp.status}: ${detail}`);
  }
}

// ── Email HTML ────────────────────────────────────────────────────────────────
// Intentionally simple — the report itself is on the linked page.
// The email is a clean, confident covering note.

function buildEmailHtml(firstName, companyName, reportUrl, senderEmail, senderName) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Your AI Opportunity Report</title>
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
    <h1>Hi ${firstName},</h1>
    <p>Great to meet you. Your bespoke AI opportunity report for ${companyName} is ready.</p>
  </div>
  <div class="body">
    <p>I've put together a report based on research into ${companyName} — covering where AI can make the biggest practical difference for a business in your position, with realistic timelines and no fluff.</p>
    <p>It includes your sector context, a primary opportunity specific to you, three quick wins you could act on in the next 90 days, and honest caveats about what to watch out for.</p>
    <div class="cta-wrap">
      <a href="${reportUrl}" class="cta-btn">View your report</a>
    </div>
    <p class="note">The report also has a PDF download button if you'd like to save or share it internally. The link doesn't expire.</p>
  </div>
  <div class="footer">
    <p><strong>${senderName}</strong> — Founder, Stackstone Consulting</p>
    <p><a href="mailto:${senderEmail}">${senderEmail}</a> &nbsp;|&nbsp; <a href="https://stackstoneconsulting.co.uk">stackstoneconsulting.co.uk</a></p>
    <p>Abingdon, Oxfordshire</p>
  </div>
</div>
</body>
</html>`;
}

// ── Telegram notify ───────────────────────────────────────────────────────────

async function notify(msg) {
  const chatId   = process.env.TELEGRAM_CHAT_ID;
  const botToken = process.env.TELEGRAM_BOT_TOKEN;
  if (!chatId || !botToken) return;
  await fetch(`https://api.telegram.org/bot${botToken}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text: `[Stackstone report] ${msg}` })
  }).catch(() => {});
}

// ── Routes ────────────────────────────────────────────────────────────────────

app.post('/send-report', requireSecret, async (req, res) => {
  // Rate limit check
  if (!rateLimitOk()) {
    console.warn('[send-report] daily rate limit reached');
    return res.status(429).json({ error: 'Daily send limit reached' });
  }

  // Validate payload
  const validationError = validatePayload(req.body);
  if (validationError) {
    console.warn(`[send-report] invalid payload: ${validationError}`);
    return res.status(400).json({ error: validationError });
  }

  const { to, companyName, reportUrl } = req.body;

  // Acknowledge immediately
  res.status(202).json({ status: 'accepted' });

  // Send async
  setImmediate(async () => {
    try {
      await sendViaGraph(req.body);
      recordSend();
      console.log(`[send-report] sent to ${to.email} — ${companyName}`);
      await notify(`Report sent to ${to.name} (${companyName}) — ${reportUrl}`);
    } catch (err) {
      console.error(`[send-report] failed for ${to.email}:`, err.message);
      await notify(`FAILED sending to ${to.name} (${companyName}): ${err.message}`);
    }
  });
});

app.get('/health', (req, res) => {
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  const sentToday = sendLog.filter(e => e.ts > cutoff).length;
  res.json({
    status: 'ok',
    service: 'stackstone-send-report',
    sentToday,
    remainingToday: MAX_PER_DAY - sentToday,
    ts: new Date().toISOString()
  });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`[send-report] listening on port ${PORT}`);
  console.log(`[send-report] rate limit: ${MAX_PER_DAY} per 24h`);
});
