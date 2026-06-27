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
- **Library dep**: `garminconnect` — the [install script](../pi-deployment.md) now **always** runs `pip3 install --upgrade garminconnect` (it used to skip the upgrade whenever the lib was already present, which stranded the Pi on old versions)
- If the account ever enables MFA, run `--setup` from a terminal so the code can be entered interactively

### First-time setup error: `[Errno 2] No such file or directory: '~/.garminconnect/oauth1_token.json'`

On a brand-new install the token dir is empty. Old `garminconnect`/`garth` versions, when handed a tokenstore path, try to **load** `oauth1_token.json` *before* falling back to a credential login — so first-time `--setup`/`/garmin_setup` fails with this `FileNotFoundError`. Two-part fix (both shipped):
- `login_and_save()` now forces a fresh credential login — it calls `client.login()` with **no** tokenstore argument (and temporarily clears `GARMINTOKENS`) so the library can never attempt the doomed load, then persists the tokens explicitly and verifies the file landed.
- The install script always upgrades the library (above), so the Pi gets the version that also falls back gracefully.

### Token save error: `'Garmin' object has no attribute 'garth'` → then false "no token file was written"

Two layered version-drift bugs in the upgraded library:

1. **Dump handle renamed.** The garth client that holds the in-memory tokens is an internal attribute of the `Garmin` object whose name changed across versions: `.garth` in older releases, `.client` in current ones. Hard-coding `client.garth.dump()` breaks on the upgraded library. `_persist_tokens()` now tries each known handle (`.garth`, then `.client`).

2. **Token filename changed (the real blocker).** The current garminconnect bundles its **own garth fork** whose `client.dump(dir)` writes a *single consolidated* `garmin_tokens.json` — **not** the legacy `oauth1_token.json` (+ `oauth2_token.json`) pair. So the dump was actually succeeding, but the post-login verification (and `--status`, and the install script) only looked for `oauth1_token.json` and wrongly reported "Login succeeded but no token file was written" — triggering pointless retries (→ 429). Detection is now filename-agnostic via `TOKEN_FILENAMES = ("garmin_tokens.json", "oauth1_token.json")` / `_token_file()`, used everywhere a token's presence/age is checked.

> **Important:** because the dump was already working, a prior "failed" setup most likely **already wrote `~/.garminconnect/garmin_tokens.json`**. After deploying this fix, run `/garmin_status` first — it should report valid tokens with no new login (and no 429 risk). Only run `/garmin_setup` again if status says tokens are missing/invalid.

> **429 caution:** every `--setup` does a real Garmin SSO login. If token-save silently failed, you'd retry repeatedly and Garmin IP-rate-limits you (`Mobile login returned 429`). The login itself usually still succeeds via a fallback transport, so once the save bug is fixed a **single** successful `--setup` is enough — do not loop on it. A hard 429 (`TooMany`) trips the [24h backoff](#auth-model--you-log-in-once); wait it out.

If you still see a failure after deploying: confirm `pip3 show garminconnect` is recent and that `~/.openclaw/.env` has `GARMIN_EMAIL`/`GARMIN_PASSWORD`.

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

### Diagnosing partial data (some fields populate, others stay `n/a`)

Symptom seen in the wild: resting HR, body battery and stress populate, but
sleep, HRV, SpO2, VO2 max, active minutes and training readiness stay `n/a`. The
working fields all come from `get_stats` / `get_body_battery` / `get_stress_data`;
every blank field comes from a *different* endpoint, so the cause is per-endpoint,
not auth. There are three distinct causes and they need different fixes:

1. **Endpoint errored** — `_call()` swallows any exception to `None` and logs
   `WARNING: <label> failed: <err>` (or `method <name>() not in this garminconnect
   version`). Grep the poller log for `WARNING.*failed` / `not in this
   garminconnect version`. Fix: upgrade `garminconnect`, or the endpoint is 404/5xx
   server-side (retry later).
2. **Data genuinely absent** — the endpoint returns `{}`/`[]` or a dict missing the
   key, with **no** warning. Common and *not a bug*: watch not worn overnight (no
   sleep/HRV/SpO2/readiness for that day), 0 intense activity (active minutes
   `n/a`), or the device model simply doesn't record that metric (older/basic
   Garmin has no HRV status / training readiness / SpO2). VO2 max only refreshes
   after a qualifying GPS run/ride.
3. **Key drift** — the endpoint returns a populated dict but under keys
   `extract()` doesn't read. No warning; field silently `n/a`.

Run **`python3 ~/.openclaw/integrations/garmin/poll-garmin.py --debug`** to tell
these apart in one shot: it prints each endpoint's type + top-level keys + a JSON
snippet, then every extracted value. The dump also goes to the poller log. (`--debug`
still writes the daily/archive files as normal.) Empty `{}`/`[]` with no warning ⇒
cause 2; populated dict whose keys don't match the extractor ⇒ cause 3 (update the
key mapping in `extract()`); a `WARNING ... failed` line ⇒ cause 1.

> **Note:** `--debug` writes raw Garmin response fragments (granular personal
> health/activity data) to the poller log. Use it temporarily for diagnosis, then
> clear/trim `poll-garmin-log.txt` — treat that log as sensitive.

Cron schedule is 09:00 (per the [06:xx/07:xx scheduling constraint](../pi-deployment.md#scheduling-constraint--avoid-06xx-and-07xx)). Log: `~/.openclaw/workspace/memory/poll-garmin-log.txt`.
