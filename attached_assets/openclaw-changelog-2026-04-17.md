# OpenClaw Changelog — 17 April 2026

## Deploy command
```bash
cd ~/openclaw && git pull && bash ~/install-forked-openclaw.sh
```

---

## 1. `attached_assets/integrations/garmin/poll-garmin-cookie.py`

**What changed:** Major auth overhaul. Previously the only auth was browser session cookies (expired every 7–14 days, required manual `--setup`). Now:

- **New primary mode**: reads `GARMIN_EMAIL` + `GARMIN_PASSWORD` from `~/.openclaw/.env`, authenticates via `garminconnect` / garth OAuth2, caches tokens to `~/.garth/`. Self-healing — no manual intervention when credentials are in `.env`.
- **Cookie mode unchanged**: still works as fallback if credentials absent or garth fails.
- `_garth_auth()`, `_garth_get()`, `_garth_safe_get()`, `_garth_display_name()`, `_fetch_all_garth()` all new.
- `get_display_name()` now tries 3 API endpoints + env var override.
- `main()` tries garth first, then cookies.
- Error messages now explicitly say to add credentials to `.env` rather than just "run --setup".

**Pi cleanup needed:**
- Nothing to delete. `garmin-cookies.json` is still valid as a fallback.
- New directory `~/.garth/` will be auto-created on first successful garth login.
- `pip3 install --break-system-packages garminconnect` — install script does this automatically.

---

## 2. `attached_assets/integrations/google/poll-calendar-google.py`

**What changed:**

- Credentials file auto-detection: tries `credentials.json` first, falls back to `gmail-credentials.json` — so a single credentials file covers both Gmail and Calendar pollers.
- Token file: `token.json` (calendar scope, separate from Gmail's `gmail-token.json`).
- `get_service()` now logs which credentials file and token file it is using.
- Error messages on missing credentials or failed OAuth now give the exact `scp` command to copy `token.json` from a desktop machine to the Pi when the Pi has no browser.
- `invalid_grant` errors now emit a `FLAG TO TOM` message with exact remediation steps.

**Pi cleanup needed:**
- Nothing to delete. If a `token.json` already exists it continues to work.
- If only `gmail-credentials.json` exists, no rename needed — the poller now picks it up automatically.
- The Calendar OAuth scope is separate from Gmail. If calendar was never authorized, `token.json` won't exist.
  - To create it, run on a machine with a browser:
    ```bash
    python3 ~/.openclaw/integrations/google/poll-calendar-google.py
    ```
  - Then SCP the token to the Pi:
    ```bash
    scp ~/.openclaw/integrations/google/token.json pi@<pi-ip>:~/.openclaw/integrations/google/token.json
    ```

---

## 3. `attached_assets/install-forked-openclaw.sh`

**Garmin section (~line 692):**
- Added `pip3 install garminconnect` step (guarded: skips if already installed).
- Updated deploy comment: cookie poller is now also a credential-auth poller.
- Install-time check: if `.env` already has `GARMIN_EMAIL` + `GARMIN_PASSWORD`, prints a confirmation instead of the old "you must run `--setup`" warning.
- Old "IMPORTANT: Run setup before the cron fires" warning is now conditional.

**Google Calendar section (~line 1397):**
- Added `pip3 install google-auth google-auth-oauthlib google-api-python-client` step (guarded: skips if already installed). Previously these were only mentioned in a warning and never actually installed — the systemd service would crash immediately with `ImportError`.
- Credential check now accepts either `credentials.json` or `gmail-credentials.json` before deciding whether to start the service.
- Warning messages when token is missing now explain the SCP workaround for headless Pi and state that Calendar auth is a separate OAuth scope from Gmail.

---

## 4. `attached_assets/integrations/mgmt-bot/mgmt-bot.py`

*(From previous session — already committed)*

- `/yt-add`, `/yt-list`, `/yt-run` Telegram commands added.
- YouTube share tracking params (`?si=`, `?feature=`, `?pp=`, `?igsh=`) stripped before dup-check.
- `_resolve_handle_to_channel_id()` added — fetches a `@handle` channel page and extracts the `UC...` ID from embedded JSON.

---

## 5. `attached_assets/integrations/youtube/channel_poller.py`

*(From previous session — already committed)*

- New file. RSS-based YouTube channel poller.
- Fetches new videos, downloads transcripts via `youtube-transcript-api`, sends AI summary to L1 via Telegram, writes to `~/.openclaw/workspace/youtube/`.
- Cron: every 30 minutes, skips `06:xx`–`07:xx`.
- Handle-to-channel-ID resolver built in.
- `youtube-transcript-api` auto-pip-installed by install script.

---

## 6. `attached_assets/integrations/youtube/channels.json`

*(From previous session — already committed)*

Channel list template. Preserved across re-installs (install script only creates it if it does not exist). L1 manages this via `/yt-add` — do not overwrite manually.

---

## Files L1 should NOT touch

| File | Reason |
|---|---|
| `~/.openclaw/integrations/garmin/garmin-cookies.json` | Still valid fallback — leave in place |
| `~/.openclaw/integrations/google/gmail-token.json` | Gmail token, unrelated to Calendar |
| `~/.garth/` | Created automatically by garth on first login — do not delete |
| `~/.openclaw/integrations/youtube/channels.json` | Runtime state managed by mgmt-bot |
