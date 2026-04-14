import { writeFileSync } from 'fs';

const W = 1600;
const H = 1100;

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

function text(x, y, content, size = 13, fill = colors.textPrimary, weight = 'normal', anchor = 'middle') {
  return `<text x="${x}" y="${y}" font-size="${size}" fill="${fill}" font-weight="${weight}" text-anchor="${anchor}" font-family="'Segoe UI', system-ui, sans-serif">${content}</text>`;
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

function component(x, y, w, h, title, subtitle, bg, border, titleColor = colors.textPrimary) {
  return `
    ${rect(x, y, w, h, bg, border, 6)}
    ${text(x + w/2, y + 16, title, 12, titleColor, '600', 'middle')}
    ${subtitle ? text(x + w/2, y + 30, subtitle, 10, colors.textSecondary, 'normal', 'middle') : ''}
  `;
}

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
  ${text(W/2, 56, 'Raspberry Pi 4 · 8 GB · L1 Agent (GPT-5.4 / Codex) · Multi-channel · Telegram-controlled', 13, colors.textSecondary, 'normal', 'middle')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- Pi outer box -->
  ${rect(20, 70, W - 40, H - 90, colors.piBox, colors.piBorder, 12)}
  ${text(45, 90, '🖥  Raspberry Pi 4 — 8 GB', 12, colors.textSecondary, '600', 'start')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- CHANNELS section (left column) -->
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
  ${text(178, 231, 'Read-only watch mode · action scanner', 10, colors.textSecondary, 'normal', 'middle')}

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

  <!-- WhatsApp -->

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- L1 AGENT (centre top) -->
  ${rect(340, 100, 480, 200, colors.agentBg, colors.agentBorder, 10)}
  ${sectionLabel(360, 108, 'L1 AGENT', colors.agentBorder)}

  <!-- Model badge -->
  ${rect(355, 128, 200, 38, '#0a1628', colors.agentBorder, 6)}
  ${text(455, 143, 'Primary Model', 10, colors.textSecondary, 'normal', 'middle')}
  ${text(455, 158, 'openai / gpt-5.4', 13, colors.blue, '700', 'middle')}

  ${rect(565, 128, 240, 38, '#0a1628', '#30363d', 6)}
  ${text(685, 143, 'Daily Reset 04:00', 10, colors.textSecondary, 'normal', 'middle')}
  ${text(685, 158, 'openai-codex / codex-1', 11, colors.textSecondary, 'normal', 'middle')}

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
  ${text(580, 289, 'openclaw-gateway.service  (systemd user unit)', 9, colors.textSecondary, 'normal', 'middle')}

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
  ${text(580, 424, 'Vector embeddings · hybrid BM25 + vector · SQLite store', 9, colors.textSecondary, 'normal', 'middle')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- INTEGRATIONS section (right column, top) -->
  ${rect(840, 100, 400, 460, colors.integrationBg, colors.integrationBorder, 8)}
  ${sectionLabel(858, 108, 'INTEGRATIONS & POLLERS', colors.integrationBorder)}

  <!-- SharePoint -->
  ${rect(855, 128, 370, 80, '#0a1a10', colors.integrationBorder, 6)}
  ${text(1040, 145, '📁  SharePoint — seerepeat.sharepoint.com', 12, colors.green, '600', 'middle')}
  ${badge(860, 154, 60, 18, 'cache/15m', '#0a1a10', colors.integrationBorder, colors.green, 9)}
  ${badge(926, 154, 60, 18, 'queue/1m', '#0a1a10', colors.integrationBorder, colors.green, 9)}
  ${badge(992, 154, 80, 18, 'binary extract', '#0a1a10', colors.integrationBorder, colors.green, 9)}
  ${badge(1078, 154, 50, 18, 'read', '#0a1a10', colors.integrationBorder, colors.green, 9)}
  ${badge(1134, 154, 80, 18, '⚠ write: needs reauth', '#1a0d00', colors.orange, colors.orange, 8)}
  ${text(1040, 198, 'Files.ReadWrite + Sites.ReadWrite.All scopes req. re-auth on assistant@', 9, colors.yellow, 'normal', 'middle')}

  <!-- Google Tasks -->
  ${rect(855, 216, 175, 50, '#0a140d', '#34a853', 6)}
  ${text(942, 234, '✅  Google Tasks', 12, '#34a853', '600', 'middle')}
  ${text(942, 249, 'create · list · complete', 10, colors.textSecondary, 'normal', 'middle')}

  <!-- Garmin -->
  ${rect(1040, 216, 185, 50, '#0d1a10', '#00b4d8', 6)}
  ${text(1132, 234, '💓  Garmin Health', 12, '#00b4d8', '600', 'middle')}
  ${text(1132, 249, 'poller: 09:00 daily', 10, colors.textSecondary, 'normal', 'middle')}

  <!-- Stackstone -->
  ${rect(855, 274, 370, 80, '#0d1a10', '#2ea043', 6)}
  ${text(1040, 292, '🏢  Stackstone Consulting', 12, colors.green, '600', 'middle')}
  ${badge(860, 302, 110, 20, 'enquiry_poller.py', '#0a1a10', '#2ea043', colors.green, 9)}
  ${badge(978, 302, 100, 20, 'report_poller.py', '#0a1a10', '#2ea043', colors.green, 9)}
  ${badge(1086, 302, 130, 20, 'retry on HTML/timeout', '#0a1a10', '#2ea043', colors.teal, 9)}
  ${text(1040, 342, 'alert suppression · Content-Type check · Stackstone CRM via SharePoint', 9, colors.textSecondary, 'normal', 'middle')}

  <!-- Microsoft email -->
  ${rect(855, 362, 175, 60, '#0d0d1a', '#0078d4', 6)}
  ${text(942, 380, '📨  Microsoft Email', 11, '#0078d4', '600', 'middle')}
  ${text(942, 395, 'assistant@ + tom@', 10, colors.textSecondary, 'normal', 'middle')}
  ${text(942, 408, '⚠ assistant token missing', 9, colors.orange, 'normal', 'middle')}

  <!-- Gmail integration -->
  ${rect(1040, 362, 185, 60, '#1a0d0d', '#ea4335', 6)}
  ${text(1132, 380, '📨  Gmail', 11, '#ea4335', '600', 'middle')}
  ${text(1132, 395, 'polling + send', 10, colors.textSecondary, 'normal', 'middle')}
  ${text(1132, 408, 'prospector: skip 06–07h', 9, colors.textSecondary, 'normal', 'middle')}

  <!-- YouTube -->
  ${rect(855, 430, 175, 50, '#1a0d0d', '#ff0000', 6)}
  ${text(942, 448, '▶  YouTube Transcript', 11, '#ff6b6b', '600', 'middle')}
  ${text(942, 463, 'native tool · Gemini fallback', 10, colors.textSecondary, 'normal', 'middle')}

  <!-- Dev command queue -->
  ${rect(1040, 430, 185, 50, '#0d1020', '#8957e5', 6)}
  ${text(1132, 448, '⚙  Dev Cmd Queue', 11, colors.purple, '600', 'middle')}
  ${text(1132, 463, '.dev-cmd.json · never exec', 10, colors.textSecondary, 'normal', 'middle')}

  <!-- Provider switch -->
  ${rect(855, 488, 370, 62, '#1a0d00', colors.orange, 6)}
  ${text(1040, 506, '🔄  Provider Switch — daily-reset.py · 04:00 cron', 12, colors.orange, '600', 'middle')}
  ${text(1040, 521, 'DBUS env vars · switches primary ↔ Codex · systemd user session', 10, colors.textSecondary, 'normal', 'middle')}
  ${text(1040, 536, 'Codex OAuth token must be refreshed or falls back to OpenAI gpt-5.4', 9, colors.yellow, 'normal', 'middle')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- MANAGEMENT BOT (bottom left) -->
  ${rect(40, 450, 280, 300, colors.infraBg, colors.infraBorder, 8)}
  ${sectionLabel(55, 458, 'MANAGEMENT BOT', colors.infraBorder)}

  ${text(180, 485, 'Telegram-controlled shell/git/npm executor', 10, colors.textSecondary, 'normal', 'middle')}

  ${[
    ['/status', '/openai', '/anthropic', '/restart'],
    ['/reboot', '/pull', '/install', '/health'],
    ['/logs', '/garmin', '/disk', '/soul'],
    ['/sp-sync', '/dev-run', '/codex', '/elevated'],
  ].map((row, ri) =>
    row.map((cmd, ci) =>
      badge(55 + ci * 65, 498 + ri * 28, 60, 22, cmd, '#1a0d0d', colors.infraBorder, colors.red, 9)
    ).join('')
  ).join('')}

  ${text(180, 615, 'All shell / git / npm execution runs through mgmt-bot', 9.5, colors.textSecondary, 'normal', 'middle')}
  ${text(180, 630, 'Gateway log: ~/.openclaw/gateway.log', 9.5, colors.textSecondary, 'normal', 'middle')}

  <!-- Scheduling constraints -->
  ${rect(55, 640, 245, 50, '#1a0d00', colors.orange, 5)}
  ${text(178, 658, '⏰  Scheduling Rules', 11, colors.orange, '600', 'middle')}
  ${text(178, 673, 'NEVER 06:xx–07:xx (prospector) · SP cache=*/15', 9, colors.textSecondary, 'normal', 'middle')}
  ${text(178, 685, 'SP queue=every min · Garmin=09:00', 9, colors.textSecondary, 'normal', 'middle')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- SKILLS / TOOLS (bottom centre) -->
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
  <!-- PENDING / KNOWN ISSUES (bottom right) -->
  ${rect(840, 570, 400, 170, '#0d0d10', '#da3633', 8)}
  ${sectionLabel(858, 578, 'KNOWN ISSUES / PENDING', '#da3633')}

  ${[
    { icon: '⚠', label: 'assistant@ Microsoft token missing — needs re-auth', color: colors.orange },
    { icon: '⚠', label: 'SharePoint write: needs Files.ReadWrite reauth on assistant@', color: colors.orange },
    { icon: '🔑', label: 'Codex OAuth: expires nightly — fallback to gpt-5.4 active', color: colors.yellow },
    { icon: '🗑', label: 'Cleanup: ~/.openclaw/integrations/tavily/ — delete', color: colors.red },
    { icon: '🗑', label: 'Cleanup: ~/.openclaw/integrations/youtube/ (old Python) — delete', color: colors.red },
  ].map((item, i) => `
    ${text(865, 604 + i * 24, item.icon, 11, item.color, 'normal', 'start')}
    ${text(882, 604 + i * 24, item.label, 10, item.color, 'normal', 'start')}
  `).join('')}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- Connection arrows (selected key flows) -->

  <!-- Telegram ↔ L1 -->
  ${arrow(320, 160, 340, 160, colors.channelBorder)}
  <!-- WhatsApp → L1 -->
  ${arrow(300, 223, 340, 200, colors.green)}
  <!-- L1 ↔ Integrations -->
  ${arrow(820, 200, 840, 200, colors.integrationBorder)}
  <!-- L1 ↔ Memory -->
  ${arrow(580, 300, 580, 310, colors.memoryBorder)}
  <!-- L1 ↔ Mgmt bot -->
  ${arrow(340, 420, 240, 460, colors.infraBorder)}

  <!-- ═══════════════════════════════════════════════════════ -->
  <!-- Deploy rule reminder -->
  ${rect(40, 760, 760, 28, '#0a0f0a', '#238636', 5)}
  ${text(420, 779, '📌  After every code change: cd ~/openclaw && git pull && bash ~/install-forked-openclaw.sh', 9.5, colors.green, 'normal', 'middle')}

  <!-- Version stamp -->
  ${text(W - 30, H - 15, 'OpenClaw Architecture · Generated 14 Apr 2026', 9, colors.textSecondary, 'normal', 'end')}
</svg>`;

writeFileSync('attached_assets/openclaw-architecture.svg', svg);
console.log('Diagram written to attached_assets/openclaw-architecture.svg');
