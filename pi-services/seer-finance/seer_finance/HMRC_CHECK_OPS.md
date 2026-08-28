# Running the HMRC staleness check on the Pi

The check is designed to run daily on the always-on Raspberry Pi (alongside
OpenClaw), not on the Windows laptop — a laptop that is asleep never fires the
reminder. The laptop is for doing the accounts work (ledger, figures) when you
sit down to it; the Pi does the unattended daily checks.

## What it does

Fetches HMRC's currently published fiscal figures and compares them to the
values held in `config.py`. It never edits `config.py`. On any change it exits
non-zero so the scheduler surfaces it and no accounting run proceeds on stale
figures. Updating a figure is always a deliberate manual edit you make after
verifying the source page.

## Exit codes

    0  all figures current — safe to proceed
    3  a figure CHANGED — stop; verify and update config.py by hand
    4  a figure could not be verified (network/parse) — check before relying

## Daily cron entry (example)

Run at 07:00 each day and capture output to a log OpenClaw can read/notify from:

    0 7 * * *  cd /home/pi/seer-finance && /usr/bin/python3 -m seer_finance.hmrc_check_cli >> /home/pi/seer-finance/hmrc_check.log 2>&1

Then have OpenClaw watch that log (or the exit status) and push you a Telegram
message on any non-zero result. The check itself stays dumb and deterministic;
OpenClaw is only the notification transport.

## Before each accounts session

Run it once by hand on the laptop too, if you like, before doing figures:

    python -m seer_finance.hmrc_check_cli

If it reports anything other than "all current", stop and reconcile before
running the ledger or preparing figures.

## When a figure has changed

1. Open the source URL the check names and confirm the new figure.
2. Add a new `FiscalConstants` entry for the new tax year in `config.py`
   (do not overwrite the old year — keep the history so prior periods stay
   reproducible).
3. Re-run the check; confirm it reports current.
4. Only then prepare figures for the affected period.
