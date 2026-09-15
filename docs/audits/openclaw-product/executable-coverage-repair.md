# Executable coverage repair

This record closes the offline coverage gaps identified in the platform and
operations audit without adding a runtime worker or changing executable
behavior. The tests use fake clients, fixture files, and a fake `curl` on
`PATH`; they do not use network credentials.

## Verified offline

| Surface                       | Coverage added or verified                                                                                                                                                                                                       | Evidence                                                               |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| YouTube transcript tool       | Bare IDs plus watch, short-link, shorts, live, embed, `/e/`, and legacy `/v/` URLs are normalized before the caption client is called. Malformed IDs fail closed.                                                                | `src/agents/tools/youtube-transcript-tool.test.ts`                     |
| YouTube transcript cache      | Equivalent URL forms share the extracted-ID cache entry.                                                                                                                                                                         | `src/agents/tools/youtube-transcript-tool.test.ts`                     |
| YouTube transcript output     | Timestamp formatting and the 80,000-character native-caption cap are covered.                                                                                                                                                    | `src/agents/tools/youtube-transcript-tool.test.ts`                     |
| YouTube fallback              | A no-caption fixture reaches the configured Gemini endpoint with the expected model, video URI, language instruction, and test-only API key. Rate-limit errors do not fall back; a missing Gemini key makes no request.          | `src/agents/tools/youtube-transcript-tool.test.ts`                     |
| Whisper API script            | Missing input, missing key, unknown arguments, successful text/JSON fixture responses, default/explicit output paths, multipart options, and a non-zero fake-`curl` exit are covered.                                            | `skills/openai-whisper-api/scripts/test_transcribe.sh`                 |
| Codex reauthentication helper | Both supported `auth-profiles.json` shapes are exercised: list-of-active-names with top-level credential and dictionary-of-credentials. Existing fields are preserved; JWT account claims and explicit `account_id` are covered. | `attached_assets/integrations/codex-reauth/test_reauth_copy_tokens.py` |
| SkilzVolt authorization       | The existing registration test denies both native tools to non-owner senders and marks both owner tools `ownerOnly`; no duplicate test was added.                                                                                | `extensions/skilzvolt/index.test.ts`                                   |

## Existing suites checked separately

The direct-exec approval, task-permit, and intake-receipt suites remain
separate from these executable fixtures. They were not broadened or copied
into this repair. Targeted runs produced:

- direct exec approval request coverage: 25 passed in
  `src/node-host/invoke-system-run.test.ts`;
- direct exec approval plan coverage: 6 passed in
  `src/node-host/invoke-system-run-plan.test.ts`;
- task permits: 6 passed in
  `attached_assets/integrations/microsoft/test_send_task_dispatch.py`;
- intake receipts and finance handoff: 34 passed across
  `pi-services/expense-intake-watcher/test_watcher.py` and
  `test_finance_handoff.py`;
- SkilzVolt extension suite: 29 passed across its four existing test files,
  including the owner-only deny test.

The intake tests were run with Python's standard-library `unittest` runner;
the environment did not provide `pytest`.

### Direct-exec PATH fixture diagnosis

The transparent `env tr` test initially failed against the unchanged baseline:
its `runCommand` mock was not called. This was an environment-specific fixture
failure, not a direct-exec implementation bug. The ambient test `PATH` resolved
`tr` from a Nix store directory, while the safe-bin policy intentionally trusts
only `/bin` and `/usr/bin` by default. Resolving the same command with
`PATH=/usr/bin:/bin` selected `/usr/bin/tr` and passed the test. The fixture now
sets that trusted system-bin `PATH` only for this case and restores the prior
value in `finally`; no security implementation or expectation was weakened.

After the test-only fix, the focused case passed (1/1), the affected
`invoke-system-run.test.ts` suite passed (25/25), and the paired approval-plan
suite passed (6/6).

## Live evidence unavailable

These tests do **not** prove live activation or delivery:

- no YouTube or Gemini request was made, so captions, region restrictions,
  rate limits, model availability, and real API authentication remain
  unverified;
- no OpenAI request was made, so account entitlement, audio decoding, API
  behavior, and deployment credentials remain unverified;
- no real Codex login, gateway restart, systemd service, or deployed agent
  profile was inspected;
- no SkilzVolt endpoint, current remote catalogue, OAuth refresh, or owner
  identity was exercised;
- no Telegram/mgmt-bot approval flow, scheduler, worker, or production intake
  receipt was run.

## Source-level findings not repaired here

The coverage work intentionally does not alter runtime behavior. Two concrete
limitations remain visible in the current code and should not be mistaken for
live failures:

1. YouTube ID extraction recognizes a string containing `?v=<11 chars>`
   without validating that its hostname is YouTube. The current tests preserve
   the documented accepted forms and do not silently turn this existing
   behavior into a new URL policy.
2. `transcribe.sh` redirects `curl` output to the destination before `curl`
   exits. A failed request therefore leaves an empty or partial output file;
   the new test verifies the non-zero exit and surfaced stderr but does not
   change that failure cleanup behavior.

These are source observations only. They are not claims that either condition
was observed in a live deployment.

## Test commands

The focused repair runs completed as follows:

- YouTube Vitest: 7 passed;
- Whisper offline shell fixture: passed;
- Codex profile-shape tests: 2 passed;
- SkilzVolt extension suite: 29 passed.
