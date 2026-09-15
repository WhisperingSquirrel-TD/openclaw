# Poller and expense branch reconciliation

**Decision:** reconcile by content against the current `main` worktree, not by
branch ancestry. No merge, cherry-pick, branch deletion, deployment, or live
runtime change was performed.

## Scope and evidence

The review was limited to:

- `attached_assets/integrations/microsoft/`
- `pi-services/expense-intake-watcher/`

The comparison was made between the current `main` tip and the snapshots of
`subrepl-fsnhqv5p` and `subrepl-g8iuhu09` in those paths. Divergent history was
not treated as proof that behavior was missing. Where current `main` already
contained the behavior, no duplicate patch was applied.

The current finance route is the XLSX/SharePoint route. The branch versions
that refer to a local Markdown ledger or SQLite capture are therefore not
valid replacements for the current route.

## `subrepl-fsnhqv5p` — Microsoft poller cleanup

| Branch change                                                                                                                                                            | Decision                                       | Current-main evidence                                                                                                                                                                                          |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `d42c78f4da0` added per-message exception handling in the email poller, malformed sent-item skipping, and startup log trimming.                                          | **Preserved; no patch needed.**                | `poll.py` already isolates malformed inbox/sent records, logs the record id, and runs `_trim_log_on_startup()` before polling.                                                                                 |
| `d42c78f4da0` added malformed-calendar-event skipping, startup log trimming, and parent-directory creation.                                                              | **Preserved; no patch needed.**                | `poll-calendar.py` already skips/logs malformed events, keeps the empty-calendar output honest, creates the log directory, and trims the log at startup.                                                       |
| `d42c78f4da0` retained the safer `--account` and explicit `--token-file` calendar selection in the branch's parent.                                                      | **Preserved; branch simplification rejected.** | Current `poll-calendar.py` retains account/token resolution. Replacing it with one hard-coded token path would regress multi-account and explicit-token operation.                                             |
| `d42c78f4da0`/`c0955d8eef2` changed `create-event.py` in a snapshot that removed `--annual` and `--all-day`, while `c0955d8eef2` clarified the missing-title error.      | **Keep current behavior; reject the removal.** | Current `create-event.py` retains both flags, annual recurrence payload construction, all-day payload construction, and the clarified `--subject`/`--title` error. The error clarification is already present. |
| The branch snapshot also removed current email trust-boundary behavior (trusted-contact registry safety checks, message identifiers, and quarantined external previews). | **Rejected as a regression.**                  | Current `poll.py` keeps the read-only trusted-contact check and external-body suppression. Poller resilience must not weaken the prompt-injection boundary.                                                    |
| Branch-local `.replit` and unrelated generated/mockup changes.                                                                                                           | **Rejected as out of scope.**                  | They do not belong to the Microsoft poller cleanup or the two owned implementation areas.                                                                                                                      |

Thus the useful cleanup from this branch was already present in current
`main`; applying the branch snapshot would have removed calendar flags,
multi-account support, or email trust protections.

## `subrepl-g8iuhu09` — blocked expense preservation

| Branch change                                                                          | Decision                        | Current-main evidence                                                                                                                                   |
| -------------------------------------------------------------------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `92d8c4c9056` stale monitored-item reconciliation.                                     | **Preserved; no patch needed.** | Current `watcher.py` has the final reconciliation pass that prunes stale active conversation rows without repeating capture or receipt work.            |
| `f5ac7a2d347` excluded `EXPENSE`-flagged rows from direct-thread supersession pruning. | **Preserved; no patch needed.** | Current `reconcile_monitored_items()` normalizes `flags` and requires `'EXPENSE' not in item_flags` before pruning.                                     |
| `f5ac7a2d347` added the blocked-direct-expense regression test.                        | **Preserved; no patch needed.** | Current `test_watcher.py` contains `test_outbound_acknowledgement_does_not_prune_blocked_direct_expense`, adapted to the current SharePoint/XLSX route. |

| Branch wording and tests that changed the canonical route to SQLite/local
`seer-expenses.md` (and removed the SharePoint boundary). | **Rejected.** | That would undo the current XLSX finance cutover, verified readback contract, and source-linked SharePoint evidence route. |
| Branch README description of the pre-cutover route. | **Rejected as stale; current documentation retained.** | The current watcher README continues to identify the XLSX workbooks and SharePoint boundary as authoritative, while documenting blocked-item retention. |

The blocked-expense behavior is therefore retained without importing the
branch's obsolete finance implementation. A later acknowledgement can
supersede ordinary direct-thread noise, but it cannot prune an active blocked
expense evidence row.

## Regression boundaries

The reconciliation intentionally leaves these behaviors intact:

1. `create-event.py --annual` creates an `absoluteYearly`/`noEnd` recurrence.
2. `create-event.py --all-day` creates an all-day Graph event with a
   date-based UTC boundary.
3. Calendar polling supports account selection and explicit token files.
4. Email polling fails closed for an unsafe trusted-contact registry and does
   not expose unsolicited external bodies.
5. Blocked `EXPENSE` monitored items survive direct-thread reconciliation.
6. Expense capture and finance handoff remain XLSX/SharePoint-authoritative;
   a branch's SQLite or local-Markdown implementation is not reintroduced.

No files were deleted and no branch was deleted.

## Verification

The owned suites were run after reconciliation:

```text
Microsoft: python3 -m unittest discover -s attached_assets/integrations/microsoft -p 'test_*.py'
Watcher:   python3 -m unittest discover -s pi-services/expense-intake-watcher -p 'test_*.py'
```

Both completed successfully: Microsoft **40 tests, OK**; watcher
**44 tests, OK**. The suites exercise guarded SharePoint/XLSX behavior and
blocked-item retention; their expected rejection messages are test output,
not live writes.

The test outcomes are recorded with the reconciliation change; these suites
are regression evidence only and do not establish live Microsoft
authentication, SharePoint availability, deployment, or scheduler delivery.
