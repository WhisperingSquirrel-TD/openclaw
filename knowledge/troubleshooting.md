# Known Failure Patterns & Diagnostics

> Part of the OpenClaw knowledge base. Map: [`../replit.md`](../replit.md).
> Related: [Pi reference: first-check diagnostics](./pi-reference.md#first-check-diagnostics--run-these-when-l1-is-silent-or-stuck) · [Pi deployment](./pi-deployment.md) · [Integrations: web search](./integrations/web-search.md)

## OpenAI model routing: codex vs standard

- `openai-codex/*` models route through the ChatGPT Plus account — subject to ChatGPT Plus usage limits (~221 min cooldown when hit)
- `openai/*` models use the standard OpenAI API key — separate limits, not affected by ChatGPT Plus cap
- Symptom of hitting the Plus cap: `[compaction] Summarization failed: You have hit your ChatGPT usage limit (plus plan)` — L1 goes silent
- Fix: switch model to `anthropic/claude-sonnet-4-5` or `openai/gpt-5.4` until limit resets (~221 min)
- **Daily reset at 4am always resets back to `openai-codex/gpt-5.4`** — this is intentional. Manual swap when cap hits, codex is the default.

## Gateway crash-loop: "Unknown model: export VAR=value"

**Fixed in source (2026-04-18).** Cause: a raw `export VAR=value` line leaked from `.env` and was written verbatim as the model string in `openclaw.json`, so the gateway couldn't resolve the model and crash-looped. Now defended in three places: `cmd_switch` (mgmt-bot) strips the `export VAR=`/trailing-`.`, the install script's `_clean_model_string` sanitizes the whole config tree on every run, and `daily-reset.py` sanitizes on read+write. If you ever see it, run `cd ~/openclaw && git pull && bash ~/install-forked-openclaw.sh` — install strips the bad value and restarts. **Rule:** never write a raw `.env` value into `openclaw.json` without stripping the `export VAR=` prefix.

## Gateway crash-loop: "plugin manifest not found" / empty `dist/extensions/` after a hand-run build

**Cause (incident 2026-06-28):** an agent edited source directly on the Pi, then ran a bare `pnpm build || true`, then restarted the gateway. The build is a multi-step chain (`tsdown-build` → `copy-plugin-sdk-root-alias` → **`copy-plugin-manifests.mjs`** → SDK dts → copy steps). On the slow Pi the build was interrupted/failed **before** `copy-plugin-manifests` ran, leaving `dist/` with bundled code but an **empty `dist/extensions/`**. The `|| true` swallowed the failure, so the gateway restarted onto the broken `dist/`. Config validation then failed with `plugins: plugin: plugin manifest not found: .../dist/extensions/<plugin>/openclaw.plugin.json` for every channel + `plugins.slots.memory: plugin not found: memory-core` → gateway exited status=1 → systemd crash-loop (`activating (auto-restart)`) → **silent on all channels** (mgmt-bot `/status` still answered, masking it). The config JSON itself was valid — this is a missing-on-disk-plugin problem, not a config-content problem.

**Fix:** revert any hand-edit (`cd ~/openclaw && git checkout -- <file>`), then run the canonical install script (`bash ~/install-forked-openclaw.sh`) which runs the **full** build chain (so `copy-plugin-manifests.mjs` actually runs) and restarts. A full rebuild from TS source on a Pi takes **~15–25 min** (not 6) — **do not interrupt it**; interrupting is what emptied `dist/extensions/` in the first place. Verify with `ls ~/openclaw/dist/extensions/` (should list telegram, whatsapp, memory-core, …) and `systemctl --user status openclaw-gateway.service` (want `active (running)`, not `activating (auto-restart)`).

**Rules:** (1) never `|| true` a build/deploy step and then restart services on top of it — a swallowed build failure means restarting onto a half-built `dist/`. (2) The install script is the single source of truth — a bare `pnpm build` is **not** equivalent (only the full chain stages plugin manifests). (3) Never hand-edit source on the Pi — change it in the repo, push (Replit Git pane), `git pull` on the Pi, run install. (4) Never `chattr +i` a git-tracked file — immutable + a repo + an install script that overwrites files = `git pull`/install can't write. (5) A "rollback" backup taken *after* a patch captures the broken state — git is the real source of truth for tracked files.

## Gateway "inactive" after `/install` (and no auto "back online" message)

**Fixed in source (2026-06-27).** Symptom: after running `/install` from the mgmt-bot, the gateway always reported **inactive** and the assistant stayed dormant until the user swapped models (or ran `/restart`) to wake it; the install wrapper also never sent a clear "back online" confirmation. **Cause:** the install's Step 12b restarted L1 via `l1-start.sh` **first**, which launches the gateway *outside* systemd — so `systemctl --user is-active openclaw-gateway.service` read "inactive". The model-switch/`/restart` path uses `systemctl --user restart`, the canonical systemd-managed start, which is why those forced it "active". The wrapper's completion tag derives from the same `is-active` check, so it reported "inconclusive" instead of "running". **Fix:** both the install script (Step 12b) and the mgmt-bot install wrapper's `gateway_up()` now **prefer `systemctl --user restart openclaw-gateway.service`** (stopping any stray `l1-start.sh` process first to avoid a port clash) and fall back to `l1-start.sh` only if systemd is unavailable. **Completion message (fixed 2026-06-27):** the install wrapper's `tg()` no longer depends on the system resolver — when the normal send hits a network/DNS error (the Pi's only resolver is Tailscale MagicDNS, which gets starved while the install pegs the CPU), it falls back to resolving `api.telegram.org` via **DNS-over-HTTPS at a literal IP** (Cloudflare `1.1.1.1` `/dns-query`, then Google `8.8.8.8` `/resolve` — both certs carry their IP as a SAN), then POSTs to Telegram **by IP with SNI=`api.telegram.org`** (cert still validated). A hardcoded Bot-API IP list is the last resort. This makes the "back online" message land even while MagicDNS is down. Wrapper diagnostics: `/tmp/openclaw-install-wrapper.log` (and `...-launch.log`).

**Completion message length cap (fixed 2026-06-27):** even with DNS solved, the completion message could still never arrive — the wrapper log showed `tg send attempt 1..18 failed: HTTP 400` (every attempt, every day) and `GAVE UP`. A 400 that persists **even after the markdown→plain-text fallback** is not a parse error: **Telegram hard-rejects any message over 4096 characters** with HTTP 400, and the message embeds the last 40 lines of install output in a code block, which easily blows past 4096. Length, not formatting, was the killer, so the plain-text fallback could never help. **Fix:** the wrapper now budgets the message — it trims the embedded log `tail` (keeping the most-recent chars, prefixed with a `…(truncated)` marker) so the whole message stays under ~3900 chars. The `tg()` HTTPError handler now also logs Telegram's response body (`e.read()[:200]`), so any future 400 states its own reason (e.g. "message is too long"), and logs the outgoing message length before sending. **Rule:** any Telegram `sendMessage` that embeds variable-length output (logs, command output, file dumps) MUST cap total length < 4096, or it 400s silently regardless of parse_mode.

**Patient gateway-status poll (fixed 2026-06-27):** the Pi can take ~6 min to fully settle after an install. The wrapper used to decide the "✅ Gateway: running" vs "⚠️ inconclusive" completion tag after a fixed ~8s sleep, so a slow box got stamped "inconclusive" even though the gateway did come up. The wrapper now polls (`wait_active`, every 5s, up to 120s; then a `gateway_up()` restart + 60s more) before deciding the tag. This runs *after* the install subprocess returns and *before* `tg()`, so it doesn't eat into `tg()`'s own 5-min send budget. Note: the ~6-min recovery is well inside the wrapper's 15-min (900s) install timeout, and the completion-message failures were always HTTP 400 (length), never timeouts.

## Outstanding items requiring Pi access

| Item | Status | Pi commands |
|------|--------|-------------|
| Desktop taskbar (LXPanel) | Unresolved — terminal and file-manager buttons disappeared after reboot | `lxpanelctl restart` to reload panel; if buttons still missing: right-click panel → Add/Remove Panel Items → add Application Launch Bar → add lxterminal and pcmanfm |
| `apply_patch`/`cron` alsoAllow warnings | Baked into OpenClaw's `coding` profile — not our config | Cannot fix without a plugin override; warnings are cosmetic |

## OpenClaw auth debugging playbook (2026-04-27)

**Symptom:** L1 silent — `⚠️ Agent failed before reply: All models failed (N): ... No API key found for provider "ollama"`

**Quick triage steps (in order):**

1. **Check gateway is running** — `openclaw logs --follow`. If "Gateway not reachable": run `openclaw doctor` → say Yes to "Start gateway service now?"
2. **Check provider cooldowns** — shown in `openclaw doctor` output. openai-codex rate-limits clear within ~40 min automatically, no action needed.
3. **Check Ollama auth** — see fix below.

**Ollama auth fix (the correct one):**

OpenClaw resolves provider auth via three paths in order:
1. `auth-profiles.json` — entries must be inside `data["profiles"]` dict, AND a matching top-level key at root level with credentials. Profiles is a **list** of name strings, not a dict — the actual credential objects ARE top-level keys.
2. **Environment variable** — `OLLAMA_API_KEY` env var (simplest, most reliable)
3. `models.json` custom `apiKey` field — unreliable, `normalizeOptionalSecretInput` may return null

**The fix that actually works:**
```bash
mkdir -p ~/.config/environment.d/
echo 'OLLAMA_API_KEY=ollama' > ~/.config/environment.d/openclaw-ollama.conf
systemctl --user daemon-reload
systemctl --user restart openclaw-gateway.service openclaw-mgmt-bot.service
```
This persists across reboots. The value `"ollama"` can be any non-empty string — Ollama doesn't validate it.

**auth-profiles.json structure (for reference):**
```json
{
  "version": 1,
  "profiles": ["anthropic:default", "openai-codex:default"],  // LIST of active profile names
  "anthropic:default": { "accessToken": "...", ... },         // top-level credential objects
  "openai-codex:default": { ... },
  "lastGood": ["anthropic"],
  "usageStats": { ... }
}
```
The `profiles` list is what OpenClaw scans. Credentials for each profile are stored as **top-level keys** (same name). Our earlier failed attempts wrote `"ollama:ollama-local"` either at top-level only (not in the list) or inside a `profiles` dict (but profiles is a list, not a dict). The env var approach bypasses all of this.

**Source file for auth logic:**
`~/openclaw/node_modules/.pnpm/openclaw@2026.2.24_*/node_modules/openclaw/dist/auth-profiles-BLqWs5Ho.js`
Search for `resolveEnvApiKey` and `getCustomProviderApiKey` to trace the lookup chain.

**auth-profiles.json is overwritten on every gateway start** — never manually edit it while the gateway or mgmt-bot is running. Always: stop both services → edit → start both.

**Services to stop/start:**
```bash
systemctl --user stop openclaw-mgmt-bot.service openclaw-gateway.service
# ... edit ...
systemctl --user start openclaw-gateway.service openclaw-mgmt-bot.service
```

**Logs location:** `/tmp/openclaw/openclaw-YYYY-MM-DD.log` (NOT journalctl — no journal files exist)
```bash
grep -i "ollama\|error\|failed" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | tail -30
```
