# Raspberry Pi Deployment

> Part of the OpenClaw knowledge base. Map: [`../replit.md`](../replit.md).
> Related: [Token efficiency](./token-efficiency.md) · [Pi reference](./pi-reference.md) · [Troubleshooting](./troubleshooting.md) · [Upstream sync](./upstream-sync.md)

## Deployment rule — always end sessions with this

**After every session where any file in this repo is changed**, always close with:

> To deploy everything changed in this session, run on the Pi:
>
> ```bash
> cd ~/openclaw && git pull
> bash ~/install-forked-openclaw.sh
> ```

- `git pull` → pulls the latest commit from GitHub
- `bash ~/install-forked-openclaw.sh` → redeploys all code, services, and skills in one command

Never assume the user knows to run this. Always say it explicitly.

**The install script is the single source of truth for deployment.** Any new file, skill, service, or integration added to the repo **must** be wired into `install-forked-openclaw.sh` or `scripts/setup-dev-workflow.sh` (which install calls) — never as a separate manual step. If a file isn't deployed by install, it doesn't count as deployed.

> Exception: the `knowledge/` docs and `replit.md` are repo-only agent reference material, not runtime files — they are intentionally not deployed to the Pi.

> Workspace ↔ GitHub note: the Replit workspace **cannot** `git push`/`pull`/`fetch` from the CLI. Push via the Replit Git pane, then run the two Pi commands above.

## Prerequisites (all handled automatically by the install script)

- **Node.js >= 22.12.0** (required by upstream since 2026.3.8 — auto-upgraded via `n`, `nvm`, or `fnm`; installs `n` if no version manager found)
- **pnpm** (installed automatically if missing)
- **Git** access to `https://github.com/WhisperingSquirrel-TD/openclaw.git`

## Install / Update

```bash
bash ~/install-forked-openclaw.sh
```

**Single command — no manual steps needed.** The script handles everything:

- Pulls the latest code from GitHub first (Step 0), before doing anything else
- Copies the freshly-pulled version of itself over `~/install-forked-openclaw.sh` and re-execs it
- This guarantees the newest script logic always runs, even if `~/install-forked-openclaw.sh` is months old
- `OPENCLAW_REEXEC=1` env var is passed through `exec` to prevent infinite re-exec loops

## What the install script does (in order)

1. Stops L1 (`~/l1-stop.sh`)
2. Uninstalls old global OpenClaw (`npm uninstall -g`, `pnpm unlink --global`)
3. Installs pnpm if missing
4. Clones or pulls the fork (`~/openclaw/`)
5. `pnpm install` (resolves dependencies)
6. `rm -rf dist && pnpm run build` (clean rebuild with tsdown)
7. `pnpm link --global` (makes `openclaw` command available)
8. Updates `~/.openclaw/openclaw.json` using `setdefault` for all fields (safe to re-run — never overwrites existing user customizations). Sets: WhatsApp watch mode, TOTP approval, exec host=gateway, watch action scanner. Type guards ensure malformed values (e.g. `null` where a dict is expected) are repaired rather than crashing.
9. Sets file protections (`chattr +a` audit log, `chattr +i` TOTP secrets, `chattr +i` config) — see [Security](./security.md)
10. Starts L1 (`~/l1-start.sh`)
11. Updates integrity hashes

It also applies the [token-efficiency config](./token-efficiency.md) defaults.

## Manual operations on the Pi

- **Stop**: `systemctl --user stop openclaw-gateway.service`
- **Start**: `systemctl --user start openclaw-gateway.service`
- **Restart**: `systemctl --user restart openclaw-gateway.service`
- **Status**: `systemctl --user status openclaw-gateway.service`
- **Quick update**: `bash ~/install-forked-openclaw.sh` — handles pull + build + config + restart automatically. If it hangs, it's waiting on `git pull` credentials.
- **Direct debug** (shows startup errors in terminal): `cd ~/openclaw && node dist/index.js gateway`
- **Config file**: `~/.openclaw/openclaw.json` (locked with `chattr +i`)
  - Unlock: `sudo chattr -i ~/.openclaw/openclaw.json`
  - Re-lock: `sudo chattr +i ~/.openclaw/openclaw.json`
- **Logs**: `~/.openclaw/gateway.log` (journald does NOT collect user logs on this Pi — always use the file). Full log map in [Pi reference](./pi-reference.md).
- **TOTP debug**: Look for "TOTP" in logs. Common issues: "unauthorized sender" (message from non-owner), "TOTP code rejected" (wrong code or replay), "approval window expired". See [TOTP](./totp.md).

## Pi restart notes

- Systemd service name is `openclaw-gateway.service` (not `openclaw`)
- journald returns "No journal files were found" for user services on this Pi — use `tail ~/.openclaw/gateway.log` instead
- The CLI entry point is `node dist/index.js` with subcommand `gateway` to run the gateway directly
- If `install-forked-openclaw.sh` hangs, it's waiting on `git pull` credentials — Ctrl+C and run steps manually
- **Config migration**: if openclaw reports `agent.*` is deprecated, run `cd ~/openclaw && node dist/index.js doctor --fix` to auto-migrate (see [Troubleshooting](./troubleshooting.md))
- **Pi performance** (from doctor): add to `~/.openclaw/.env` for faster CLI starts:
  ```
  NODE_COMPILE_CACHE=/var/tmp/openclaw-compile-cache
  OPENCLAW_NO_RESPAWN=1
  ```
  And: `mkdir -p /var/tmp/openclaw-compile-cache`

## Background services (Pi)

- Python pollers must run as **systemd user services**, not bare background processes. They will not survive a Pi reboot or openclaw restart otherwise. The install script creates `openclaw-email-microsoft` and `openclaw-email-gmail` services automatically. Full service list in [Pi reference](./pi-reference.md#systemd-user-services-on-this-pi).
- `loginctl enable-linger $USER` is required so user services start at boot without a login session. The install script applies this.
- If a service shows `inactive (dead)` after install, check whether credentials/token files exist — the services are intentionally not started until auth is complete.

## After every install on the Pi

- Check `systemctl --user status openclaw-email-microsoft` and `openclaw-email-gmail` — both should show `active (running)`.
- Check `tail ~/.openclaw/workspace/memory/poll-microsoft-log.txt` and `poll-gmail-log.txt` — should show `Poll complete` lines.
- If feeds are stale: check logs for auth errors first (expired token), then check service status. See [Integrations: Microsoft](./integrations/microsoft.md) / [Google](./integrations/google.md).

## Scheduling constraint — avoid 06:xx and 07:xx

The CRM runs at 06:00 every morning and another job runs at 07:00. No background jobs should be scheduled in the 06:xx or 07:xx windows. All timed tasks should be scheduled at 08:00 or later. The Garmin poller is set to 09:00 for this reason. **Enforce this for any new pollers or cron jobs added in future.**
