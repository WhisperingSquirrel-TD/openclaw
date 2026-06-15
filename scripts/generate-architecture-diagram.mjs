import { writeFileSync } from 'fs';

const W = 1600;
const H = 1065;

const colors = {
  bg: '#0d1117',
  piBox: '#161b22',
  piBorder: '#30363d',
  channelBg: '#0d2137',
  channelBorder: '#1f6feb',
  integrationBg: '#0d2218',
  integrationBorder: '#238636',
  memoryBg: '#1a1025',
  memoryBorder: '#8957e5',
  toolsBg: '#1a1000',
  toolsBorder: '#d29922',
  infraBg: '#1a0d0d',
  infraBorder: '#da3633',
  agentBg: '#0d1f3c',
  agentBorder: '#388bfd',
  secBg: '#1f1206',
  secBorder: '#f0883e',
  l2Bg: '#07222a',
  l2Border: '#56d4dd',
  cyan: '#7ee8f2',
  sharepointBg: '#0a1a10',
  textPrimary: '#e6edf3',
  textSecondary: '#8b949e',
  textAccent: '#58a6ff',
  green: '#3fb950',
  yellow: '#d29922',
  purple: '#bc8cff',
  red: '#ff7b72',
  orange: '#ffa657',
  blue: '#79c0ff',
  teal: '#39d353',
};

function rect(x, y, w, h, fill, stroke, rx = 8, opacity = 1) {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${fill}" stroke="${stroke}" stroke-width="1.5" opacity="${opacity}"/>`;
}

function xmlEscape(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function text(x, y, content, size = 13, fill = colors.textPrimary, weight = 'normal', anchor = 'middle') {
  return `<text x="${x}" y="${y}" font-size="${size}" fill="${fill}" font-weight="${weight}" text-anchor="${anchor}" font-family="'Segoe UI', system-ui, sans-serif">${xmlEscape(content)}</text>`;
}

function badge(x, y, w, h, label, bg, border, textColor = colors.textPrimary, fontSize = 11) {
  return `
    ${rect(x, y, w, h, bg, border, 5)}
    ${text(x + w/2, y + h/2 + 4, label, fontSize, textColor, 'normal', 'middle')}
  `;
}

function sectionLabel(x, y, label, color) {
  return `
    <rect x="${x}" y="${y}" width="10" height="14" rx="2" fill="${color}"/>
    ${text(x + 16, y + 11, label, 12, color, '600', 'start')}
  `;
}

function line(x1, y1, x2, y2, color = colors.piBorder, dash = '') {
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="1.2" ${dash ? `stroke-dasharray="${dash}"` : ''} opacity="0.7"/>`;
}

function arrow(x1, y1, x2, y2, color = colors.piBorder) {
  const dx = x2 - x1, dy = y2 - y1;
  const len = Math.sqrt(dx*dx + dy*dy);
  const ux = dx/len, uy = dy/len;
  const ax = x2 - ux*8 - uy*5, ay = y2 - uy*8 + ux*5;
  const bx = x2 - ux*8 + uy*5, by = y2 - uy*8 - ux*5;
  return `
    <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="1.2" opacity="0.7"/>
    <polygon points="${x2},${y2} ${ax},${ay} ${bx},${by}" fill="${color}" opacity="0.7"/>
  `;
}

// ── Management bot commands (real, from mgmt-bot.py dispatch table) ──
const mgmtCommands = [
  ['/status', '/health', '/logs', '/disk'],
  ['/restart', '/reboot', '/pull', '/install'],
  ['/openai', '/anthropic', '/codex', '/codexmini'],
  ['/garmin', '/sp-sync', '/soul', '/yt-list'],
  ['/yt-run', '/dev-run', '/dev-test', '/cancel'],
];

// ── Security & control features (from replit.md / src/infra) ──
const securityFeatures = [
  ['🔐 TOTP Approval', 'RFC 6238 · replay-protected · 5-min window'],
  ['🛡 Trust Gate', 'trustLevel ≥ 1 → owner approval'],
  ['👁 Watch Mode', 'WhatsApp read-only · JSONL transcript'],
  ['📝 Outbound Audit Log', 'append-only JSONL · chattr +a'],
  ['⏱ Rate Limiter', 'per-minute / per-hour · queue | drop'],
  ['🧱 Session Isolation', 'channel-isolated outbound context'],
  ['📌 Immutable System Prompt', 'injected before SOUL.md'],
  ['🔒 SOUL.md Integrity', 'SHA-256 integrity check per session'],
  ['🗝 Encrypted SOUL at Rest', 'AES-256-GCM · vault passphrase'],
  ['⛔ Exec Denylist', 'chattr / config / totp / audit blocked'],
  ['🕵 Obfuscation Detector', 'base64 / heredoc / eval (hardened mode)'],
  ['🚫 Per-Channel denyCommands', 'calendar.* · react · camera · contacts'],
];

// ── Ops notes & gotchas (durable, from replit.md + incident lessons) ──
const opsNotes = [
  ['⏰', 'No cron 06:xx–07:xx (CRM / prospector) · jobs ≥ 08:00', colors.yellow],
  ['🔑', 'Codex OAuth refresh nightly → fallback to gpt-5.4', colors.yellow],
  ['📧', 'Microsoft: one /ms-reauth grants ALL scopes (unified)', colors.orange],
  ['🧩', 'Plugin manifest needs id — bad stub aborts all channels', colors.orange],
  ['📄', 'Triage via ~/.openclaw/gateway.log (not /logs — Garmin noise)', colors.blue],
  ['🗓', 'SharePoint housekeeping 02:00 · Anthropic batch API', colors.green],
  ['✅', '"active" service ≠ assistant working — always send a test msg', colors.orange],
];

const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <defs>
    <filter id="glow">
      <feGaussianBlur stdDeviation="2" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>

  <!-- Background -->
  <rect width="${W}" height="${H}" fill="${colors.bg}"/>

  <!-- Title -->
  ${text(W/2, 36, 'OpenClaw — Personal AI Gateway', 22, colors.textAccent, '700', 'middle')}
  ${text(W/2, 56, 'Raspberry Pi 4 · 8 GB · Multi-channel L1 Agent · Telegram-controlled · TOTP-gated · audit-logged', 12.5, colors.textSecondary, 'normal', 'middle')}

  <!-- Confidence legend (this is a working sketch, not a verified source-of-truth diagram) -->
  ${rect(1185, 11, 392, 52, '#0c1117', '#30363d', 6)}
  ${text(1195, 26, 'CONFIDENCE — working draft, not source-of-truth', 8.2, colors.textSecondary, '700', 'start')}
  ${text(1195, 42, '✅ live / verified        🟠 designed (in code)', 9, colors.textSecondary, 'normal', 'start')}
  ${text(1195, 57, '🔌 pluggable / unverified        🚧 evolving', 9, colors.textSecondary, 'normal', 'start')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- Pi outer box -->
  ${rect(20, 70, W - 40, 805, colors.piBox, colors.piBorder, 12)}
  ${text(45, 90, '🖥  Raspberry Pi 4 — 8 GB · systemd user services (linger enabled)', 12, colors.textSecondary, '600', 'start')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- CHANNELS section (left column, top) -->
  ${rect(40, 100, 280, 320, colors.channelBg, colors.channelBorder, 8)}
  ${sectionLabel(55, 108, 'CHANNELS', colors.channelBorder)}

  <!-- Telegram -->
  ${rect(55, 130, 245, 60, '#0d2137', colors.channelBorder, 6)}
  ${text(130, 148, '✈  Telegram', 13, colors.blue, '600', 'middle')}
  ${text(178, 165, '2-way · management bot · TOTP gate', 10, colors.textSecondary, 'normal', 'middle')}
  ${badge(200, 150, 85, 18, 'MGMT BOT', '#0a1628', colors.channelBorder, colors.blue, 9)}

  <!-- WhatsApp -->
  ${rect(55, 198, 245, 50, '#0d1f0d', '#25d366', 6)}
  ${text(178, 216, '📱  WhatsApp', 13, colors.green, '600', 'middle')}
  ${text(178, 231, 'Watch mode · action scanner · 🚧 evolving', 10, colors.textSecondary, 'normal', 'middle')}

  <!-- Gmail -->
  ${rect(55, 256, 116, 50, '#1a0d0d', '#ea4335', 6)}
  ${text(113, 274, '📧  Gmail', 12, '#ea4335', '600', 'middle')}
  ${text(113, 289, 'polling · send', 10, colors.textSecondary, 'normal', 'middle')}

  <!-- Microsoft / Outlook -->
  ${rect(179, 256, 121, 50, '#0d1020', '#0078d4', 6)}
  ${text(239, 274, '📧  Outlook', 12, '#0078d4', '600', 'middle')}
  ${text(239, 289, 'polling · send', 10, colors.textSecondary, 'normal', 'middle')}

  <!-- Discord -->
  ${rect(55, 314, 245, 45, '#0d0d1a', '#5865f2', 6)}
  ${text(178, 332, '🎮  Discord', 12, '#7289da', '600', 'middle')}
  ${text(178, 347, 'owner-locked DM only', 10, colors.textSecondary, 'normal', 'middle')}

  <!-- More channels -->
  ${rect(55, 367, 245, 45, '#0c1018', '#30363d', 6)}
  ${text(178, 384, '＋ Signal · Slack · iMessage · Matrix', 10, colors.textSecondary, 'normal', 'middle')}
  ${text(178, 399, 'IRC · LINE · Feishu · Google Chat · 🔌 pluggable', 9, colors.textSecondary, 'normal', 'middle')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- MANAGEMENT BOT (left column, bottom) -->
  ${rect(40, 440, 280, 360, colors.infraBg, colors.infraBorder, 8)}
  ${sectionLabel(55, 448, 'MANAGEMENT BOT', colors.infraBorder)}
  ${text(180, 470, 'Python Telegram bot · shell / git / npm executor', 9, colors.textSecondary, 'normal', 'middle')}

  ${mgmtCommands.map((row, ri) =>
    row.map((cmd, ci) =>
      badge(50 + ci * 66, 482 + ri * 26, 62, 22, cmd, '#1a0d0d', colors.infraBorder, colors.red, 8.5)
    ).join('')
  ).join('')}

  ${text(180, 626, '＋ /sp-housekeep · /ms-reauth · /ms-reauth-personal · /ai-briefing', 8.3, colors.textSecondary, 'normal', 'middle')}
  ${text(180, 640, '＋ /wcp-up · /wcp-url · /dev-pause/resume/queue · /help · /start', 8.3, colors.textSecondary, 'normal', 'middle')}
  ${text(180, 656, '✅ real commands from mgmt-bot dispatch — run /help for the live list', 8, colors.green, 'normal', 'middle')}

  <!-- WCP -->
  ${rect(50, 674, 260, 46, '#0a1628', colors.channelBorder, 5)}
  ${text(180, 691, '🌐  WCP — Workspace Control Panel', 10, colors.blue, '600', 'middle')}
  ${text(180, 706, 'on-demand quick tunnel · /wcp-up · /wcp-url', 9, colors.textSecondary, 'normal', 'middle')}

  ${text(180, 736, 'All shell / git / npm execution runs through mgmt-bot', 9, colors.textSecondary, 'normal', 'middle')}
  ${text(180, 750, 'Out-of-band control even if the gateway is down', 9, colors.textSecondary, 'normal', 'middle')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- L1 AGENT (centre top) -->
  ${rect(340, 100, 480, 200, colors.agentBg, colors.agentBorder, 10)}
  ${sectionLabel(360, 108, 'L1 AGENT', colors.agentBorder)}

  <!-- Model badge -->
  ${rect(355, 128, 200, 38, '#0a1628', colors.agentBorder, 6)}
  ${text(455, 143, 'Primary Model', 10, colors.textSecondary, 'normal', 'middle')}
  ${text(455, 158, 'openai / gpt-5.4', 13, colors.blue, '700', 'middle')}

  ${rect(565, 128, 240, 38, '#0a1628', '#30363d', 6)}
  ${text(685, 143, 'Switchable · Ollama local fallback', 10, colors.textSecondary, 'normal', 'middle')}
  ${text(685, 158, 'anthropic · codex · gemini · copilot', 11, colors.textSecondary, 'normal', 'middle')}

  <!-- Tools profile -->
  ${rect(355, 174, 200, 28, '#0c1520', '#30363d', 5)}
  ${text(455, 191, 'profile: coding + alsoAllow: youtube_transcript', 9, colors.yellow, 'normal', 'middle')}

  <!-- TOTP gate -->
  ${rect(565, 174, 240, 28, '#1a0d00', colors.orange, 5)}
  ${text(685, 191, '🔐  TOTP Approval Gate · 5-min window', 9.5, colors.orange, 'normal', 'middle')}

  <!-- Trust level -->
  ${rect(355, 210, 200, 24, '#0c1520', '#30363d', 5)}
  ${text(455, 226, 'trustLevel: 1 · approvalMode: totp', 9, colors.textSecondary, 'normal', 'middle')}

  <!-- Exec -->
  ${rect(565, 210, 240, 24, '#0c1520', '#30363d', 5)}
  ${text(685, 226, 'exec.host: gateway · security: allowlist', 9, colors.textSecondary, 'normal', 'middle')}

  <!-- Gateway log -->
  ${rect(355, 242, 450, 24, '#0c1520', '#30363d', 5)}
  ${text(580, 258, '📄  Gateway log: ~/.openclaw/gateway.log · StandardOutput=append', 9, colors.textSecondary, 'normal', 'middle')}

  <!-- Systemd -->
  ${rect(355, 274, 450, 22, '#0a0d10', '#30363d', 5)}
  ${text(580, 289, 'openclaw-gateway.service  (Fastify ws + http · systemd user unit)', 9, colors.textSecondary, 'normal', 'middle')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- MEMORY section (centre, below agent) -->
  ${rect(340, 310, 480, 130, colors.memoryBg, colors.memoryBorder, 8)}
  ${sectionLabel(360, 318, 'QMD MEMORY SYSTEM', colors.memoryBorder)}

  ${rect(355, 338, 140, 50, '#130d1a', colors.memoryBorder, 5)}
  ${text(425, 354, '📖  SOUL.md', 12, colors.purple, '600', 'middle')}
  ${text(425, 369, 'immutable identity', 9.5, colors.textSecondary, 'normal', 'middle')}

  ${rect(505, 338, 140, 50, '#130d1a', colors.memoryBorder, 5)}
  ${text(575, 354, '🧠  MEMORY.md', 12, colors.purple, '600', 'middle')}
  ${text(575, 369, 'working knowledge', 9.5, colors.textSecondary, 'normal', 'middle')}

  ${rect(655, 338, 155, 50, '#1a0d1a', '#6e3686', 5)}
  ${text(732, 354, '⏳  SOUL_PENDING.md', 11, '#bc8cff', '600', 'middle')}
  ${text(732, 369, 'never auto-promote', 9.5, '#da3633', 'normal', 'middle')}

  ${rect(355, 396, 450, 34, '#0d0a14', '#30363d', 5)}
  ${text(580, 410, 'memory_search · memory_get · sessions_list · sessions_history', 10, colors.textSecondary, 'normal', 'middle')}
  ${text(580, 424, 'Vector embeddings · hybrid BM25 + vector · LanceDB / SQLite store', 9, colors.textSecondary, 'normal', 'middle')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- SKILLS / TOOLS (centre, below memory) -->
  ${rect(340, 450, 480, 210, colors.toolsBg, colors.toolsBorder, 8)}
  ${sectionLabel(358, 458, 'SKILLS & TOOLS (L1 Callable)', colors.toolsBorder)}

  ${[
    { label: 'read / write / edit', color: colors.yellow },
    { label: 'exec (gateway host)', color: colors.yellow },
    { label: 'process / cron', color: colors.yellow },
    { label: 'sessions_list / history / send', color: colors.yellow },
    { label: 'sessions_spawn / subagents', color: colors.yellow },
    { label: 'memory_search / memory_get', color: colors.purple },
    { label: 'image', color: colors.yellow },
    { label: 'session_status', color: colors.yellow },
    { label: 'youtube_transcript ✅ (alsoAllow)', color: colors.green },
    { label: 'multi_tool_use.parallel', color: colors.yellow },
  ].map((t, i) => {
    const col = i < 5 ? 0 : 1;
    const row = i < 5 ? i : i - 5;
    const x = 355 + col * 240;
    const y = 480 + row * 32;
    return `
      ${rect(x, y, 228, 26, '#0f0c00', colors.toolsBorder, 4)}
      ${text(x + 114, y + 17, t.label, 10, t.color, 'normal', 'middle')}
    `;
  }).join('')}

  <!-- Future / not yet exposed -->
  ${rect(355, 642, 460, 15, '#0a0a0a', '#30363d', 3)}
  ${text(585, 653, 'web_search · web_fetch · browser · canvas — NOT in coding profile', 9, colors.textSecondary, 'normal', 'middle')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- DEPLOYMENT & GIT SYNC (centre, bottom) -->
  ${rect(340, 675, 480, 175, '#0a140d', colors.integrationBorder, 8)}
  ${sectionLabel(358, 683, 'DEPLOYMENT & GIT SYNC', colors.integrationBorder)}

  ${rect(355, 702, 450, 24, '#0a0f0a', '#30363d', 5)}
  ${text(580, 718, 'install-forked-openclaw.sh — single source of truth (pull → build → config → restart)', 8.8, colors.green, 'normal', 'middle')}

  ${rect(355, 730, 450, 22, '#0c1218', '#30363d', 5)}
  ${text(580, 745, 'systemd user units: gateway · email-microsoft · email-gmail · pollers', 9, colors.textSecondary, 'normal', 'middle')}

  ${text(580, 772, 'Sync:  Workspace ──Git pane──▶ GitHub ──git pull──▶ Pi', 10, colors.blue, '600', 'middle')}
  ${text(580, 788, 'reverse: Pi ──push──▶ GitHub ──Pull──▶ Workspace  (workspace CLI push blocked)', 9, colors.textSecondary, 'normal', 'middle')}

  ${rect(355, 800, 450, 28, '#0a0f0a', colors.integrationBorder, 5)}
  ${text(580, 818, '📌  cd ~/openclaw && git pull && bash ~/install-forked-openclaw.sh   ( or /install )', 9.2, colors.green, 'normal', 'middle')}
  ${text(580, 843, '🚧 push / backup health visibility recently tightened — still stabilising', 8.2, colors.yellow, 'normal', 'middle')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- INTEGRATIONS section (col 3, top) -->
  ${rect(840, 100, 400, 455, colors.integrationBg, colors.integrationBorder, 8)}
  ${sectionLabel(858, 108, 'INTEGRATIONS & POLLERS  ✅', colors.integrationBorder)}

  <!-- SharePoint -->
  ${rect(855, 128, 370, 80, '#0a1a10', colors.integrationBorder, 6)}
  ${text(1040, 145, '📁  SharePoint — shared store (mirror + tidy)', 12, colors.green, '600', 'middle')}
  ${badge(860, 154, 60, 18, 'cache/15m', '#0a1a10', colors.integrationBorder, colors.green, 9)}
  ${badge(926, 154, 60, 18, 'queue/1m', '#0a1a10', colors.integrationBorder, colors.green, 9)}
  ${badge(992, 154, 84, 18, 'binary extract', '#0a1a10', colors.integrationBorder, colors.green, 9)}
  ${badge(1082, 154, 132, 18, 'housekeep 02:00 · batch API', '#0a1a10', colors.integrationBorder, colors.teal, 8.5)}
  ${text(1040, 198, 'fed by L2 · tidied by L1 (shared store below) · Files.ReadWrite + Sites.ReadWrite.All', 9, colors.yellow, 'normal', 'middle')}

  <!-- Google Tasks -->
  ${rect(855, 216, 175, 50, '#0a140d', '#34a853', 6)}
  ${text(942, 234, '✅  Google Tasks', 12, '#34a853', '600', 'middle')}
  ${text(942, 249, 'create · list · complete', 10, colors.textSecondary, 'normal', 'middle')}

  <!-- Garmin -->
  ${rect(1040, 216, 185, 50, '#0d1a10', '#00b4d8', 6)}
  ${text(1132, 234, '💓  Garmin Health', 12, '#00b4d8', '600', 'middle')}
  ${text(1132, 249, '09:00 · garth creds self-heal', 9.5, colors.textSecondary, 'normal', 'middle')}

  <!-- Microsoft email -->
  ${rect(855, 274, 175, 60, '#0d0d1a', '#0078d4', 6)}
  ${text(942, 292, '📨  Microsoft Email', 11, '#0078d4', '600', 'middle')}
  ${text(942, 307, 'assistant@ + tom@', 10, colors.textSecondary, 'normal', 'middle')}
  ${text(942, 320, 'systemd: email-microsoft', 9, colors.textSecondary, 'normal', 'middle')}

  <!-- Gmail integration -->
  ${rect(1040, 274, 185, 60, '#1a0d0d', '#ea4335', 6)}
  ${text(1132, 292, '📨  Gmail', 11, '#ea4335', '600', 'middle')}
  ${text(1132, 307, 'polling + send', 10, colors.textSecondary, 'normal', 'middle')}
  ${text(1132, 320, 'systemd: email-gmail', 9, colors.textSecondary, 'normal', 'middle')}

  <!-- Calendar / Tasks -->
  ${rect(855, 342, 370, 46, '#0d0d1a', '#0078d4', 6)}
  ${text(1040, 360, '📅  Microsoft Calendar + Tasks (poll-calendar.py)', 11, '#4ea3e0', '600', 'middle')}
  ${text(1040, 375, 'calendar writes go ONLY through MS integration (calendar.* denied)', 8.8, colors.yellow, 'normal', 'middle')}

  <!-- YouTube -->
  ${rect(855, 396, 175, 50, '#1a0d0d', '#ff0000', 6)}
  ${text(942, 414, '▶  YouTube Transcript', 11, '#ff6b6b', '600', 'middle')}
  ${text(942, 429, 'native tool · channel poller', 10, colors.textSecondary, 'normal', 'middle')}

  <!-- Dev command queue -->
  ${rect(1040, 396, 185, 50, '#0d1020', '#8957e5', 6)}
  ${text(1132, 414, '⚙  Dev Cmd Queue', 11, colors.purple, '600', 'middle')}
  ${text(1132, 429, '.dev-cmd.json · review/exec', 9.5, colors.textSecondary, 'normal', 'middle')}

  <!-- Provider switch -->
  ${rect(855, 454, 370, 62, '#1a0d00', colors.orange, 6)}
  ${text(1040, 472, '🔄  Provider Switch 🟠 — daily-reset.py · 04:00 cron', 12, colors.orange, '600', 'middle')}
  ${text(1040, 487, 'switches primary ↔ Codex via systemd user-session env (DBUS)', 9.5, colors.textSecondary, 'normal', 'middle')}
  ${text(1040, 502, 'Codex OAuth must be fresh, else falls back to OpenAI gpt-5.4', 9, colors.yellow, 'normal', 'middle')}

  <!-- AI briefing -->
  ${rect(855, 524, 370, 24, '#0a140d', '#2ea043', 5)}
  ${text(1040, 540, '🗞  AI Briefing — /ai-briefing (status · run · read)', 9.5, colors.green, 'normal', 'middle')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- OPS NOTES & GOTCHAS (col 3, bottom) -->
  ${rect(840, 570, 400, 280, '#0d0d10', '#da3633', 8)}
  ${sectionLabel(858, 578, 'OPS NOTES & GOTCHAS', '#da3633')}

  ${opsNotes.map((item, i) => `
    ${text(865, 606 + i * 27, item[0], 11, item[2], 'normal', 'start')}
    ${text(884, 606 + i * 27, item[1], 9.3, item[2], 'normal', 'start')}
  `).join('')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- SECURITY & CONTROL (col 4, full height) -->
  ${rect(1250, 100, 325, 750, colors.secBg, colors.secBorder, 8)}
  ${sectionLabel(1268, 108, 'SECURITY & CONTROL  🟠 DESIGNED', colors.secBorder)}

  ${securityFeatures.map((f, i) => {
    const y = 128 + i * 54;
    return `
      ${rect(1262, y, 300, 46, '#160d04', colors.secBorder, 5)}
      ${text(1272, y + 18, f[0], 11, colors.orange, '600', 'start')}
      ${text(1272, y + 34, f[1], 9, colors.textSecondary, 'normal', 'start')}
    `;
  }).join('')}

  ${text(1412, 782, '🟠 implemented in code — verify live on the Pi before relying on these', 8.2, colors.yellow, 'normal', 'middle')}
  ${text(1412, 798, 'config chattr +i · audit chattr +a · totp secret chattr +i', 8.5, colors.textSecondary, 'normal', 'middle')}
  ${text(1412, 814, 'denylist intended to run before TOTP (open window should not bypass)', 8.5, colors.red, 'normal', 'middle')}
  ${text(1412, 832, 'Telegram owner-only · unauthorized senders rejected', 8.5, colors.textSecondary, 'normal', 'middle')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- Connection arrows (selected key flows) -->

  <!-- Telegram ↔ L1 -->
  ${arrow(320, 160, 340, 160, colors.channelBorder)}
  <!-- WhatsApp → L1 -->
  ${arrow(300, 223, 340, 200, colors.green)}
  <!-- L1 ↔ Integrations -->
  ${arrow(820, 200, 840, 200, colors.integrationBorder)}
  <!-- Integrations ↔ Security -->
  ${arrow(1240, 200, 1250, 200, colors.secBorder)}
  <!-- L1 ↔ Memory -->
  ${arrow(580, 300, 580, 310, colors.memoryBorder)}
  <!-- L1 ↔ Mgmt bot -->
  ${arrow(340, 420, 240, 440, colors.infraBorder)}
  <!-- Memory ↔ Skills -->
  ${arrow(580, 440, 580, 450, colors.toolsBorder)}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- EXTERNAL: L2 AGENT ↔ SHARED SHAREPOINT ↔ L1 (below the Pi) -->
  ${rect(40, 895, W - 80, 150, '#08161a', '#2a5b63', 12)}
  ${sectionLabel(60, 905, 'EXTERNAL AGENT & SHARED SHAREPOINT STORE', colors.cyan)}

  <!-- L2 Agent (separate system) -->
  ${rect(70, 932, 380, 96, colors.l2Bg, colors.l2Border, 8)}
  ${text(86, 954, '🤖  L2 Agent — Meeting Minutes', 13, colors.cyan, '700', 'start')}
  ${badge(364, 938, 78, 17, 'SEPARATE', '#07222a', colors.l2Border, colors.cyan, 8)}
  ${text(86, 976, 'captures meeting minutes · tips · stories', 10, colors.textSecondary, 'normal', 'start')}
  ${text(86, 994, 'writes .md + files into the SharePoint folder', 10, colors.textSecondary, 'normal', 'start')}
  ${text(86, 1014, 'runs outside the Pi · its own agent / LLM', 9, colors.textSecondary, 'normal', 'start')}

  <!-- SharePoint shared store (hub) -->
  ${rect(610, 924, 380, 112, colors.sharepointBg, colors.integrationBorder, 10)}
  ${text(626, 948, '📁  SharePoint — Shared Store', 14, colors.green, '700', 'start')}
  ${badge(906, 932, 70, 17, 'SHARED', '#0a1a10', colors.integrationBorder, colors.green, 8)}
  ${text(626, 972, 'meeting-minutes folder · Stackstone CRM', 10, colors.textSecondary, 'normal', 'start')}
  ${text(626, 990, 'Microsoft 365 · Files.ReadWrite · Sites.ReadWrite.All', 9.5, colors.textSecondary, 'normal', 'start')}
  ${text(626, 1012, 'L2 fills it ▸ L1 tidies it · gateway mirrors this store', 9, colors.yellow, 'normal', 'start')}

  <!-- L1 housekeeping (this Pi) -->
  ${rect(1150, 932, 380, 96, '#0d1f3c', colors.agentBorder, 8)}
  ${text(1166, 954, '🧹  L1 Housekeeping — tidies up', 13, colors.blue, '700', 'start')}
  ${badge(1462, 938, 52, 17, 'ON PI', '#0a1628', colors.agentBorder, colors.blue, 8)}
  ${text(1166, 976, 'sharepoint_housekeeping.py · 02:00 · batch API', 9.5, colors.textSecondary, 'normal', 'start')}
  ${text(1166, 994, 'rename → canonical dates · create/refresh Current.md', 9.5, colors.textSecondary, 'normal', 'start')}
  ${text(1166, 1014, 'safe auto-writes · ambiguous items reported', 9, colors.textSecondary, 'normal', 'start')}

  <!-- Flow: L2 → SharePoint → L1 -->
  ${text(530, 968, 'writes', 9, colors.cyan, '600', 'middle')}
  ${arrow(452, 980, 608, 980, colors.l2Border)}
  ${text(1070, 962, 'reads', 9, colors.green, '600', 'middle')}
  ${arrow(992, 974, 1148, 974, colors.integrationBorder)}
  ${text(1070, 1004, 'tidies back', 9, colors.blue, '600', 'middle')}
  ${arrow(1148, 992, 992, 992, colors.agentBorder)}
  <!-- shared store ↔ gateway mirror (connects up to the Pi box) -->
  ${line(990, 924, 1040, 877, colors.integrationBorder, '5 4')}
  ${text(1052, 905, '↕ same store mirrored by the gateway above', 8.5, colors.integrationBorder, 'normal', 'start')}

  <!-- Version stamp -->
  ${text(W - 30, H - 12, 'OpenClaw Architecture · Generated 15 Jun 2026', 9, colors.textSecondary, 'normal', 'end')}
</svg>`;

writeFileSync('attached_assets/openclaw-architecture.svg', svg);
console.log('Diagram written to attached_assets/openclaw-architecture.svg');
