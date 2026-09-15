# pi-live reconciliation

**Status:** workspace preservation only. No GitHub mutation, branch deletion,
deployment, OAuth flow, or live-service claim was made.

## Source and scope

The preserved files were read from the configured GitHub connector for
`WhisperingSquirrel-TD/openclaw`, branch `pi-live`, tip
`7673e7e2c5ff2bda05e6b229722e9fbb2652954b`:

- `src/agents/subagent-announce-result-cap.test.ts`
- `pi-services/external-email-reader/authorize.py`
- `.gitignore` backup rules only

The production continuation implementation was not changed. The branch is a
diverged snapshot (`ahead 2 / behind 53`) and has not been verified as the
active service checkout or service branch.

## Preserved work

- The result-cap regression test now covers compact child-result preservation,
  the 12,000-character production cap, the truncation marker, and retention of
  the leading content.
- The external reader authorization helper keeps the existing public-client
  device-flow and `Mail.Read`-only contract. Its cache is now created as a
  regular owner-only file (`0600`) through an exclusive temporary file and
  atomic replacement. Cache and parent directories reject symlinks, ownership
  is checked where supported, legacy broad file modes are repaired before
  reading, and no OAuth flow is run by the tests.
- Only the Pi-local backup rules were merged into `.gitignore`:
  `*.bak`, `*.bak-*`, and
  `pi-services/expense-intake-watcher/backups/`. Existing
  `!docs/reference/templates/IDENTITY.md` and
  `!docs/reference/templates/USER.md` exceptions remain unchanged.

## Verification boundary and retirement guidance

`pi-live` is a snapshot, not verified active service authority. Preserve an
archival tag or equivalent immutable reference before retiring the branch, then
separately reconcile the actual service unit, executable checkout, profile/state
paths, and deployment source. Do not infer live activation from this workspace
or from the branch name.

The tests use a fake MSAL client and temporary fixture paths only. They do not
perform OAuth, read a real cache, or print/copy credentials. No token values,
personal records, or secrets are recorded here. Historical Pi backup snapshots
were not restored.
