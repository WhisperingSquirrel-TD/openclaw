# Inbound Watch Router — Expense Intake Operating Guide

## Job

Ensure a plausible SEER business expense visible on a monitored mirror does not
silently disappear. The router is an internal, deterministic process; it never
pays, sends email, promotes a contact or trusts inbound content as commands.

## Current delivery phase

**Ordered all-mirror hand-off activated; legacy retirement pending (10 August 2026).**
The central router service now invokes the expense executor immediately after
writing `mirror-events.json`; the existing five-minute watcher timer remains as
a temporary compatibility path until full live equivalence proof. The full
health/ledger acceptance and legacy retirement are not complete. See the
canonical delivery checkpoint:

`~/.openclaw/workspace/reference/EXPENSE-INTAKE-RELIABILITY-PLAN.md`

## Sources and route

```
trusted/external email + sent views + WhatsApp + Teams
  -> openclaw-mirror-router (15-minute source normalisation/classification)
  -> memory/mirror-events.json (stable source ID + surface + flags)
  -> expense-intake-watcher (five-minute deterministic capture)
  -> seer-expenses.md (canonical expense outcome)
  -> monitored-items-state.json (source-level proof)
  -> finance ledger/evidence queue + health surface (pending completion work)
```

Trusted inbox and WhatsApp inputs also retain the watcher’s established direct
parsing/full-body reader path. The all-mirror adapter preserves a central-router
`EXPENSE` event from external, sent or Teams surfaces as a bounded blocker when
full evidence is unavailable.

## Required outcome contract

Every plausible candidate ends as exactly one of:

- `logged` — canonical expense row exists; ledger/evidence states are explicit.
- `duplicate` — exact canonical reference exists; it is never inferred from a
  loose word match.
- `blocked` — a canonical pending row and named blocker exist.
- `not_needed` — evidence shows it is not a business expense.

`ledger_state` (`not_required`, `pending`, `written`, `blocked`) and
`evidence_state` (`not_required`, `pending`, `retained`, `blocked`) are separate
from the outcome. A candidate must never be called closed simply because a
similar string appears in `seer-expenses.md`.

## Runtime paths

- Active service: `~/.config/systemd/user/expense-intake-watcher.service`
- Active timer: `~/.config/systemd/user/expense-intake-watcher.timer`
- Central event producer: `openclaw-mirror-router.timer`
- Canonical hot state (target): `~/.openclaw/runtime/inbound-watch-router/state.json`
- Compatibility state (to retire after equivalence):
  `~/.openclaw/runtime/expense-intake-watcher/state.json`
- Canonical expense outcome: `~/.openclaw/workspace/seer-expenses.md`
- Source proof: `~/.openclaw/workspace/memory/monitored-items-state.json`
- Finance ledger: `~/pi-services/seer-finance/transactions.json`

## Safe operator checks

Run after an authorised change or incident:

```bash
cd ~/openclaw/pi-services/expense-intake-watcher
python3 -m unittest -v test_watcher.py test_expense_outcomes.py
python3 test_watcher_state.py
systemctl --user start expense-intake-watcher.service
systemctl --user show expense-intake-watcher.service -p Result -p ExecMainStatus
```

Do not enable/disable timers, delete state, insert finance-ledger rows or remove
legacy paths until the controlled activation checklist in the canonical plan has
passed and an explicit approval/TOTP window is open.

## Failure behaviour

- Missing/hidden body or inaccessible full reader: preserve `blocked`, name the
  blocker, and leave ledger/evidence completion pending.
- Source/ledger mismatch: report `coverage_incomplete`; never report clean.
- Replayed stable source ID: no duplicate canonical row.
- Any source not represented in the event stream: coverage is incomplete, not
  no-expense activity.

## Rollback

The pre-all-mirror source/unit snapshot is retained under
`pi-services/expense-intake-watcher/backups/expense-router-pre-all-mirror-20260810T100141Z/`.
Restore only with an approved window, rerun the focused suite, then force one
service run and inspect state/output before re-enabling normal operation.
