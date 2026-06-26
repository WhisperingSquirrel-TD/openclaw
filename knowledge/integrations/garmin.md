# Integration: Garmin Poller

> Part of the OpenClaw knowledge base. Map: [`../../replit.md`](../../replit.md) · Knowledge index: [`../README.md`](../README.md).
> Related: [Pi deployment: scheduling](../pi-deployment.md#scheduling-constraint--avoid-06xx-and-07xx) · [Pi reference: logs](../pi-reference.md) · [Troubleshooting](../troubleshooting.md)

## garminconnect library (DI OAuth, login once)

`poll-garmin.py` is the single canonical poller, built on the maintained
[`cyberjunky/python-garminconnect`](https://github.com/cyberjunky/python-garminconnect)
library (Garmin's current DI OAuth flow). The old cookie poller
(`poll-garmin-cookie.py`) and the legacy garth poller are **retired and deleted** —
both cookie scraping (deprecated `/proxy/` paths returned empty `{}`) and direct
garth logins (Cloudflare-blocked + per-account 429 bans lasting 24–72h) are dead ends.

## Auth model — you log in ONCE

- **Setup** (`--setup`, or `/garmin-setup` on Telegram): reads `GARMIN_EMAIL` +
  `GARMIN_PASSWORD` from `~/.openclaw/.env`, logs in (MFA prompt only if the
  account has MFA — this account does not), and caches a self-renewing token in
  `~/.garminconnect/` (`oauth1_token.json` + `oauth2_token.json`).
- **Scheduled run** (cron, 09:00): constructs the client with **no credentials**
  and resumes from the cached token, auto-refreshing it. It can therefore **never
  fall through to a credential login** — the path that caused the 429 spiral is
  structurally impossible from cron.
- **Token-rejected / missing**: the run logs a `FLAG TO TOM` to re-run setup and
  exits cleanly — it never retries a login.
- **429 guard**: any 429 writes `~/.openclaw/integrations/garmin/.garmin_429_backoff`;
  for the next 24h all runs skip immediately so a ban is never made worse.

## Data collected

For L1 exercise/recovery advice: resting HR, post-workout
recovery HR (from activity details), HRV (last night / status / weekly), **training
readiness** (Garmin's recovery-readiness score), sleep stages + score, SpO2,
stress, Body Battery high/low, VO2max, steps/calories/intensity minutes, and recent
activities. Written to `GARMIN_DAILY.md` (full snapshot) and `GARMIN_ARCHIVE.md`
(rolling 28-day compact history).

- **Script**: `~/.openclaw/integrations/garmin/poll-garmin.py`
- **Token cache**: `~/.garminconnect/` (override dir via `GARMINTOKENS` env var)
- **Commands**: `--setup` (one-time login), `--status` (token validity/age, never
  logs in), `--backfill N` (N days of history into the archive); plus mgmt-bot
  `/garmin`, `/garmin-setup`, `/garmin-status`
- **Library dep**: `garminconnect` — installed/upgraded automatically by the [install script](../pi-deployment.md)
- If the account ever enables MFA, run `--setup` from a terminal so the code can be entered interactively

## Data source / field extraction

The poller no longer talks to `/gc-api/` endpoints directly — the `garminconnect`
library owns all endpoint mapping, Cloudflare handling, and token refresh. Field
extraction lives in `poll-garmin.py::extract()`, which reads the library's typed
responses (`get_stats`, `get_heart_rates`, `get_hrv_data`, `get_sleep_data`,
`get_spo2_data`, `get_stress_data`, `get_training_readiness`, `get_body_battery`,
`get_max_metrics`, `get_activities` / `get_activity`). Note the library exposes
`get_rhr_day` / `get_heart_rates` — there is **no** `get_resting_heart_rate`. If a
field is missing on a given account/device the poller writes `n/a` and continues;
upgrade the library (`pip3 install --break-system-packages --upgrade garminconnect`)
if Garmin changes a response shape.

Cron schedule is 09:00 (per the [06:xx/07:xx scheduling constraint](../pi-deployment.md#scheduling-constraint--avoid-06xx-and-07xx)). Log: `~/.openclaw/workspace/memory/poll-garmin-log.txt`.
