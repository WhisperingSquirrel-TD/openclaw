export function ArchDiagram() {
  return (
    <div className="min-h-screen bg-[#0a0e1a] text-white font-['Inter'] p-6 overflow-auto">
      <div className="max-w-[1380px] mx-auto space-y-4">

        {/* Title */}
        <div className="text-center mb-2">
          <h1 className="text-2xl font-bold tracking-widest text-cyan-400 uppercase">OpenClaw · L1 Architecture</h1>
          <p className="text-xs text-slate-500 mt-1">Raspberry Pi 4 · 8GB · Personal AI Gateway</p>
        </div>

        {/* EXTERNAL SERVICES ROW */}
        <Section label="EXTERNAL WORLD" color="border-slate-600" labelColor="text-slate-400">
          <div className="flex flex-wrap gap-3 justify-center">
            <ExtBadge icon="✈️" label="Telegram" sub="Bot API" color="bg-sky-950 border-sky-700" />
            <ExtBadge icon="📱" label="WhatsApp" sub="Baileys / Read-only" color="bg-green-950 border-green-700" />
            <ExtBadge icon="🏢" label="Microsoft 365" sub="Graph API · MAPI" color="bg-blue-950 border-blue-700" />
            <ExtBadge icon="📂" label="SharePoint" sub="Sites · Libraries" color="bg-blue-950 border-blue-800" />
            <ExtBadge icon="📧" label="Gmail" sub="IMAP / API" color="bg-red-950 border-red-700" />
            <ExtBadge icon="⌚" label="Garmin Connect" sub="Health API" color="bg-teal-950 border-teal-700" />
            <ExtBadge icon="✅" label="Google Tasks" sub="REST API" color="bg-green-950 border-green-800" />
            <ExtBadge icon="🏗️" label="Stackstone CRM" sub="Reports · Enquiries" color="bg-orange-950 border-orange-700" />
            <ExtBadge icon="🐙" label="GitHub" sub="Repos · PRs" color="bg-slate-800 border-slate-600" />
            <ExtBadge icon="▲" label="Vercel" sub="Preview URLs" color="bg-slate-800 border-slate-500" />
            <ExtBadge icon="🧠" label="Anthropic / OpenAI" sub="claude-sonnet-4-5 · gpt-5.4" color="bg-violet-950 border-violet-700" />
          </div>
        </Section>

        {/* POLLERS + CHANNELS ROW */}
        <div className="grid grid-cols-2 gap-4">

          {/* CHANNELS */}
          <Section label="CHANNELS" color="border-sky-800" labelColor="text-sky-400">
            <div className="grid grid-cols-3 gap-3">
              <ChannelCard
                title="Telegram"
                badge="2-WAY"
                badgeColor="bg-sky-700"
                icon="✈️"
                items={["Messages in/out", "Commands & approvals", "TOTP gate on writes", "Mgmt-bot control"]}
                color="border-sky-800"
              />
              <ChannelCard
                title="WhatsApp"
                badge="READ-ONLY"
                badgeColor="bg-green-800"
                icon="📱"
                items={["Baileys watch mode", "Logs to WHATSAPP_FEED.md", "No sends / no replies", "Contact mapping"]}
                color="border-green-800"
              />
              <ChannelCard
                title="Email"
                badge="POLL"
                badgeColor="bg-blue-800"
                icon="📧"
                items={["tom@ + assistant@", "Gmail IMAP", "→ MICROSOFT_INBOX.md", "→ GMAIL_INBOX.md"]}
                color="border-blue-800"
              />
            </div>
          </Section>

          {/* POLLERS */}
          <Section label="POLLERS  ·  CRON JOBS" color="border-amber-800" labelColor="text-amber-400">
            <div className="grid grid-cols-2 gap-2">
              <PollerRow icon="📂" label="SharePoint Cache" schedule="*/15 min" detail="Syncs files → local cache · auto-extracts binaries" color="text-blue-300" />
              <PollerRow icon="📋" label="SharePoint Queue" schedule="every 1 min" detail="Processes write queue · read_binary on-demand" color="text-blue-300" />
              <PollerRow icon="📧" label="Microsoft Mail" schedule="*/5 min" detail="MAPI poll · deduplicates · appends to feed" color="text-sky-300" />
              <PollerRow icon="✉️" label="Gmail" schedule="*/5 min" detail="IMAP poll · threads · appends to feed" color="text-red-300" />
              <PollerRow icon="⌚" label="Garmin Health" schedule="09:00 daily" detail="Steps · sleep · HRV · stress → GARMIN_HEALTH.md" color="text-teal-300" />
              <PollerRow icon="🏗️" label="Stackstone" schedule="*/10 min" detail="Reports + enquiries → STACKSTONE_FEED.md" color="text-orange-300" />
              <PollerRow icon="❤️" label="Health Check" schedule="daily" detail="System self-test · Telegram notification" color="text-pink-300" />
              <PollerRow icon="🔍" label="Prospector" schedule="08:xx" detail="Pipeline sweep · opportunity scoring" color="text-yellow-300" />
            </div>
          </Section>
        </div>

        {/* CORE L1 GATEWAY */}
        <Section label="L1 · CORE AI GATEWAY  (Raspberry Pi 4 · 8GB)" color="border-violet-600" labelColor="text-violet-300">
          <div className="grid grid-cols-4 gap-4">

            {/* SOUL / MEMORY */}
            <div className="bg-[#1a1040] border border-violet-700 rounded-lg p-3 space-y-2">
              <div className="text-xs font-bold text-violet-300 uppercase tracking-wider mb-2">Memory System</div>
              <MemCard icon="🔮" label="SOUL.md" sub="Core personality · baked identity" color="text-violet-300" />
              <MemCard icon="📔" label="MEMORY.md" sub="Long-term working memory" color="text-indigo-300" />
              <MemCard icon="⏳" label="SOUL_PENDING.md" sub="Staging — never auto-promoted" color="text-amber-300" />
              <MemCard icon="🔒" label="SOUL.md.enc" sub="Vault copy · encrypted" color="text-slate-400" />
            </div>

            {/* SECURITY */}
            <div className="bg-[#0f1a10] border border-green-800 rounded-lg p-3 space-y-2">
              <div className="text-xs font-bold text-green-400 uppercase tracking-wider mb-2">Security</div>
              <MemCard icon="🔑" label="TOTP Approval" sub="Write-gate on outbound actions" color="text-green-300" />
              <MemCard icon="🚫" label="Exec Denylist" sub="SECURITY_DENY_PATTERNS scan" color="text-red-300" />
              <MemCard icon="📋" label="Outbound Audit Log" sub="Every external call logged" color="text-yellow-300" />
              <MemCard icon="🛡️" label="QMD Memory" sub="Quantised markdown document store" color="text-cyan-300" />
            </div>

            {/* FEEDS */}
            <div className="bg-[#0f1520] border border-cyan-800 rounded-lg p-3 space-y-2">
              <div className="text-xs font-bold text-cyan-300 uppercase tracking-wider mb-2">Feed Files</div>
              <FeedFile label="MICROSOFT_INBOX.md" />
              <FeedFile label="GMAIL_INBOX.md" />
              <FeedFile label="WHATSAPP_FEED.md" />
              <FeedFile label="GARMIN_HEALTH.md" />
              <FeedFile label="STACKSTONE_FEED.md" />
              <FeedFile label="SHAREPOINT_INDEX.md" />
              <FeedFile label="GOOGLE_TASKS.md" />
            </div>

            {/* DEV WORKFLOW */}
            <div className="bg-[#160f10] border border-rose-800 rounded-lg p-3 space-y-2">
              <div className="text-xs font-bold text-rose-300 uppercase tracking-wider mb-2">Dev Workflow</div>
              <MemCard icon="📝" label=".dev-cmd.json" sub="One-at-a-time command queue" color="text-rose-300" />
              <MemCard icon="⏸️" label=".dev-cmd-paused" sub="Pause flag for dev queue" color="text-amber-300" />
              <MemCard icon="🔄" label="6-Skill Pipeline" sub="plan→init→build→test→deploy→patch" color="text-green-300" />
              <MemCard icon="📸" label=".preview-state.json" sub="Vercel preview URL per project" color="text-blue-300" />
            </div>
          </div>
        </Section>

        {/* SKILLS + MGMT BOT ROW */}
        <div className="grid grid-cols-3 gap-4">

          {/* SKILLS */}
          <div className="col-span-2">
            <Section label="SKILLS  ·  L1 READS  (~/.openclaw/skills/)" color="border-emerald-700" labelColor="text-emerald-400">
              <div className="grid grid-cols-3 gap-2">
                <SkillCard icon="📋" name="app-plan" desc="Spec + architecture blueprint" step="1" />
                <SkillCard icon="🔧" name="app-init" desc="Scaffold repo · CI · secrets" step="2" />
                <SkillCard icon="⚙️" name="app-build" desc="Feature development loop" step="3" />
                <SkillCard icon="🧪" name="app-test" desc="Test suite + QA pass" step="4" />
                <SkillCard icon="🚀" name="app-deploy" desc="Vercel deploy + preview URL" step="5" />
                <SkillCard icon="🩹" name="app-patch" desc="Bug fixes post-deploy" step="6" />
                <SkillCard icon="▶️" name="app-resume" desc="Resume from checkpoint" step="↩" />
                <SkillCard icon="🤖" name="mgmt-bot" desc="Shell / git / npm execution" step="🔑" />
                <SkillCard icon="📂" name="sharepoint" desc="Read · write · binary extract" step="SP" />
              </div>
            </Section>
          </div>

          {/* MGMT BOT */}
          <Section label="MANAGEMENT BOT  ·  Telegram" color="border-rose-700" labelColor="text-rose-400">
            <div className="space-y-2">
              <div className="text-xs text-slate-400 mb-2">Executes all shell/git/npm — L1 never runs directly</div>
              <CmdRow cmd="/install" desc="pip / npm package installs" />
              <CmdRow cmd="/dev-run" desc="Queues .dev-cmd.json entry" />
              <CmdRow cmd="/dev-test" desc="Runs test suite via queue" />
              <CmdRow cmd="/soul" desc="SOUL_PENDING.md review" />
              <CmdRow cmd="/status" desc="System health snapshot" />
              <CmdRow cmd="/logs" desc="Tail service logs" />
              <div className="mt-3 pt-2 border-t border-slate-700">
                <div className="text-xs text-slate-400 mb-1">Vercel Preview State</div>
                <div className="text-xs text-blue-300 font-mono">_save_preview_state()</div>
                <div className="text-xs text-slate-500 mt-1">Deletes old preview · tracks per project</div>
              </div>
            </div>
          </Section>
        </div>

        {/* SHAREPOINT BINARY + STORAGE */}
        <div className="grid grid-cols-2 gap-4">

          {/* SHAREPOINT BINARY EXTRACTION */}
          <Section label="SHAREPOINT  ·  BINARY EXTRACTION" color="border-blue-700" labelColor="text-blue-300">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <div className="text-xs text-slate-400 mb-1">Supported formats</div>
                <FormatBadge ext=".docx" lib="python-docx" color="bg-blue-900/50 border-blue-700" />
                <FormatBadge ext=".pdf" lib="pdfminer.six" color="bg-red-900/50 border-red-700" />
                <FormatBadge ext=".pptx" lib="python-pptx" color="bg-orange-900/50 border-orange-700" />
                <FormatBadge ext=".msg" lib="extract-msg" color="bg-slate-800 border-slate-600" />
              </div>
              <div className="space-y-2">
                <div className="text-xs text-slate-400 mb-1">Output</div>
                <div className="text-xs text-green-300 font-mono">*.extracted.md</div>
                <div className="text-xs text-slate-500">Auto-extracted every 15 min</div>
                <div className="text-xs text-slate-500">On-demand via read_binary queue</div>
                <div className="text-xs text-slate-500">Max 5 MB · images optional</div>
                <div className="mt-2 pt-2 border-t border-slate-700">
                  <div className="text-xs text-slate-400">sharepoint_binary_extractor.py</div>
                  <div className="text-xs text-slate-500">+ cache poller auto-hook</div>
                  <div className="text-xs text-slate-500">+ queue processor read_binary op</div>
                </div>
              </div>
            </div>
          </Section>

          {/* STORAGE */}
          <Section label="STORAGE  ·  ~/.openclaw/" color="border-slate-600" labelColor="text-slate-400">
            <div className="grid grid-cols-2 gap-2">
              <StorePath icon="📁" path="workspace/projects/" desc="App workspaces (symlinked)" />
              <StorePath icon="💾" path="workspace/sharepoint-cache/" desc="SP file mirror + .extracted.md" />
              <StorePath icon="📚" path="skills/" desc="9 skill markdown files" />
              <StorePath icon="🧠" path="SOUL.md · MEMORY.md" desc="Core identity + memory" />
              <StorePath icon="⏳" path="SOUL_PENDING.md" desc="Staging — needs human review" />
              <StorePath icon="📋" path="workspace/.dev-cmd.json" desc="Active dev command queue" />
              <StorePath icon="📸" path=".preview-state.json" desc="Per-project Vercel preview" />
              <StorePath icon="📊" path="SHAREPOINT_INDEX.md" desc="Full SP manifest + extracted" />
            </div>
          </Section>
        </div>

        {/* FOOTER */}
        <div className="text-center text-xs text-slate-600 pt-2 border-t border-slate-800">
          All deployments via <span className="text-slate-500">ln -sf</span> symlinks ·
          Models: <span className="text-slate-500">anthropic/claude-sonnet-4-5</span> ·
          <span className="text-slate-500"> openai/gpt-5.4</span> ·
          Never exec from L1 — always queue via mgmt-bot
        </div>

      </div>
    </div>
  );
}

function Section({ label, color, labelColor, children }: { label: string; color: string; labelColor: string; children: React.ReactNode }) {
  return (
    <div className={`border ${color} rounded-xl p-4 bg-[#0d1220]/60`}>
      <div className={`text-xs font-bold tracking-widest uppercase ${labelColor} mb-3`}>{label}</div>
      {children}
    </div>
  );
}

function ExtBadge({ icon, label, sub, color }: { icon: string; label: string; sub: string; color: string }) {
  return (
    <div className={`border rounded-lg px-3 py-2 text-center min-w-[100px] ${color}`}>
      <div className="text-xl mb-1">{icon}</div>
      <div className="text-xs font-semibold text-white">{label}</div>
      <div className="text-[10px] text-slate-400 mt-0.5">{sub}</div>
    </div>
  );
}

function ChannelCard({ title, badge, badgeColor, icon, items, color }: { title: string; badge: string; badgeColor: string; icon: string; items: string[]; color: string }) {
  return (
    <div className={`border ${color} rounded-lg p-3 bg-[#0a0e1a]`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">{icon}</span>
        <span className="text-sm font-semibold text-white">{title}</span>
        <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold text-white ml-auto ${badgeColor}`}>{badge}</span>
      </div>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className="text-[11px] text-slate-400 flex items-start gap-1">
            <span className="text-slate-600 mt-0.5">·</span>{item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function PollerRow({ icon, label, schedule, detail, color }: { icon: string; label: string; schedule: string; detail: string; color: string }) {
  return (
    <div className="flex items-start gap-2 bg-[#0a0e1a] border border-slate-800 rounded-lg p-2">
      <span className="text-base mt-0.5">{icon}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold ${color}`}>{label}</span>
          <span className="text-[10px] text-amber-400 font-mono ml-auto whitespace-nowrap">{schedule}</span>
        </div>
        <div className="text-[10px] text-slate-500 mt-0.5 truncate">{detail}</div>
      </div>
    </div>
  );
}

function MemCard({ icon, label, sub, color }: { icon: string; label: string; sub: string; color: string }) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-sm mt-0.5">{icon}</span>
      <div>
        <div className={`text-xs font-semibold font-mono ${color}`}>{label}</div>
        <div className="text-[10px] text-slate-500">{sub}</div>
      </div>
    </div>
  );
}

function FeedFile({ label }: { label: string }) {
  return (
    <div className="text-[11px] font-mono text-cyan-300/80 bg-cyan-950/20 border border-cyan-900/40 rounded px-2 py-0.5">
      {label}
    </div>
  );
}

function SkillCard({ icon, name, desc, step }: { icon: string; name: string; desc: string; step: string }) {
  return (
    <div className="bg-emerald-950/30 border border-emerald-800/50 rounded-lg p-2">
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-sm">{icon}</span>
        <span className="text-xs font-mono font-bold text-emerald-300">{name}</span>
        <span className="ml-auto text-[10px] bg-emerald-900 text-emerald-300 px-1.5 py-0.5 rounded font-bold">{step}</span>
      </div>
      <div className="text-[10px] text-slate-400">{desc}</div>
    </div>
  );
}

function CmdRow({ cmd, desc }: { cmd: string; desc: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-mono text-rose-300 bg-rose-950/40 border border-rose-800/40 rounded px-1.5 py-0.5 min-w-[80px]">{cmd}</span>
      <span className="text-[11px] text-slate-400">{desc}</span>
    </div>
  );
}

function FormatBadge({ ext, lib, color }: { ext: string; lib: string; color: string }) {
  return (
    <div className={`flex items-center gap-2 border rounded px-2 py-1 ${color}`}>
      <span className="text-xs font-mono font-bold text-white">{ext}</span>
      <span className="text-[10px] text-slate-400 ml-auto">{lib}</span>
    </div>
  );
}

function StorePath({ icon, path, desc }: { icon: string; path: string; desc: string }) {
  return (
    <div className="bg-slate-900/40 border border-slate-700/50 rounded-lg p-2">
      <div className="flex items-start gap-1.5">
        <span className="text-sm">{icon}</span>
        <div>
          <div className="text-[11px] font-mono text-slate-300">{path}</div>
          <div className="text-[10px] text-slate-500 mt-0.5">{desc}</div>
        </div>
      </div>
    </div>
  );
}
