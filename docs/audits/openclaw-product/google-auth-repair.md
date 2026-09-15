# Google auth source/skill repair proposal

**Status:** source repair implemented; governed skill proposal submitted and
pending human review

**Proposal ID:** `ffd8f32c-24c7-4cce-b71d-880fc5cf834d`
**Actual MCP status:** `pending` (`review_mode: human`,
`next_action: await_human_review`, `merge_state: clean`)

**Scope:** Google Calendar and Gmail poller OAuth only

**Live skill inspected:** `google-auth`

**Pinned live version:** `d0dda1c9-8f0e-4ce8-a54d-5f8ed80629c7`
**Live content SHA-256:** `4a0ed0bbbdc8ffbdf78d2f7d0d48c5f0d0f3e9690fdf0fc655fc8e4b9a68f17f`
**Proposed content SHA-256:** `c004860f229eb69753c554c3ccec5161738a86448d99a157290034b69e7a9fbd`

## Finding

The pinned live body says to use a phone-first callback, but the checked-in
Calendar poller previously called `InstalledAppFlow.run_local_server()` and
documented an SSH tunnel. The live body also names a Calendar `auth.py` helper
that is not in this checkout, uses a user-specific absolute path, and does not
describe Gmail's separate interactive route. Gmail could also attempt
interactive OAuth from a systemd process when its token was missing.

This was a source/contract contradiction, not evidence that a deployed service
or credential failed. No live service, OAuth consent, callback, token, or
network auth was used during this repair.

## Source repair

The poller source now has an explicit, offline-testable phone-first route:

- Calendar: `poll-calendar-google.py --auth`, with the installed-app
  loopback redirect `http://localhost:8765/`.
- Gmail: `gmail_poll.py --auth`, with the separate loopback redirect
  `http://localhost:8766/`.
- The operator opens the standard Google authorization URL on the phone and
  pastes the complete final localhost callback into the waiting terminal
  prompt. The poller validates the exact HTTP localhost origin, port, path,
  required code and state, and the authorization-attempt state before calling
  the OAuth library's normal `fetch_token` token exchange. After validation,
  the in-memory callback is narrowly rewritten to HTTPS solely for oauthlib's
  secure-transport parser, matching `run_local_server`; no TLS checks or
  network transport settings are disabled.
- Both installed-app flow constructors explicitly request PKCE verifier
  generation (`autogenerate_code_verifier=True`) so the auth-code request and
  token exchange carry a verifier even where the library default is `None`.
- Both phone-first authorization requests include `prompt=consent`, forcing
  Google to issue a refresh-capable grant when a prior grant would otherwise
  omit the refresh token.
- Callback URLs are never printed by the poller and are not accepted as
  tokens. The route does not use deprecated out-of-band OAuth, invented
  request keys, or arbitrary callback URLs.
- The explicit auth commands do not delete an existing token before a
  replacement attempt, and reject a replacement that lacks a refresh token.
  New and refreshed tokens are atomically written with owner-only (`0600`)
  permissions. A confirmed `invalid_grant` refresh failure by a running
  Calendar poller is still an incomplete recovery until a refresh-capable
  replacement and readback succeed.
- OAuth failure output does not echo provider responses or the pasted callback.
- A systemd Gmail process no longer starts interactive OAuth without a TTY; it
  emits the explicit `--auth` recovery route instead.
- Expired credentials without a refresh token fail closed because unattended
  pollers require a refresh token. Confirmed `invalid_grant` refresh failures
  retain the existing Calendar token and require explicit replacement auth.

The source changes are limited to:

- `attached_assets/integrations/google/poll-calendar-google.py`
- `attached_assets/integrations/google/gmail_poll.py`
- `attached_assets/integrations/google/test_google_auth.py`

The runtime agent updated the deployment/auth guidance separately; this source
task did not modify installer files. Installer deployment, service activation,
and a fresh feed remain operational checks rather than claims proven here.

## Offline evidence

`test_google_auth.py` loads both pollers with stubbed Google modules and does
not read a real token or contact Google. It covers:

- exact localhost callback origin, port, code, and state validation;
- standard authorization URL plus full callback handoff;
- failure preserving an existing token;
- private atomic token write and readback;
- refusal to start Gmail OAuth from a non-interactive service;
- Calendar feed freshness-marker readback;
- expired-token refresh-token requirement and invalid-grant token retention;
- preservation of existing tokens when a replacement lacks a refresh token;
- real oauthlib callback/state/PKCE/token-parser integration with a stubbed
  token HTTP response (when the optional OAuth libraries are installed).

The focused offline suite passed locally:

```text
Ran 13 tests ... OK (skipped=1)
```

The one skipped test is the real-library integration test because the base
environment lacks `google-auth-oauthlib`/`oauthlib`; the package-management
install attempt was blocked by the immutable system site-packages path. The
other tests use dependency stubs and no real token. This is not live OAuth or
service proof.

## Proposed sanitized live skill correction

The following is a proposal for the owning skill. It is deliberately
portable: it has no personal hostnames, absolute home-directory names, or
credential values. It is submitted as the governed proposal above; the live
approved skill remains unchanged until human review accepts it.

````markdown
---
name: google-auth
description: Re-authorize Google Calendar and Gmail integrations when OAuth tokens are missing, revoked, stale, or failing to refresh; use the phone-first route when the gateway host is remote.
---

# Google Auth

Use this skill for Google OAuth recovery on the gateway host.

## Scope

- Google Calendar poller re-auth
- Gmail poller re-auth
- Token-missing / token-revoked recovery
- Stale Google feed recovery when the root cause is auth

## Phone-first Calendar route

1. Confirm the failing component from the local poller reference and its
   relevant log/output file.
2. If shell access is gated, ask the operator to open the gate first.
3. Before directing this route, verify that the deployed poller supports
   `--auth` (for example, `--help` lists it). If it does not, stop and report
   that source/installer rollout is required; do not claim the gateway host or
   Pi is updated, and do not claim auth is complete.
4. Run:

   ```bash
   python3 ~/.openclaw/integrations/google/poll-calendar-google.py --auth
   ```
````

5. Open the printed Google consent URL on the phone.
6. After consent, copy the complete final callback URL beginning with
   `http://localhost:8765/` and paste it into the waiting auth prompt on the
   gateway host. Do not paste a token or put the callback in shell history.
7. Restart the Calendar service:

   ```bash
   systemctl --user restart openclaw-calendar-google.service
   ```

8. Verify the service is running, `GOOGLE_CALENDAR.md` has a fresh
   `Last updated:` marker, and the Calendar log shows a successful update.

## Phone-first Gmail route

1. Confirm the failing Gmail component and relevant log/output file.
2. Verify that the deployed `gmail_poll.py --help` lists `--auth`. If it does
   not, stop and report that source/installer rollout is required; do not claim
   the gateway host or Pi is updated, and do not claim Gmail auth is complete.
3. Run:

   ```bash
   python3 ~/.openclaw/integrations/google/gmail_poll.py --auth
   ```

4. Open the printed consent URL on the phone and paste the complete final
   callback beginning with `http://localhost:8766/` into the waiting prompt.
5. Restart `openclaw-email-gmail.service`.
6. Verify the service and the Gmail feed/log have refreshed.

## Rules

- Treat full callback URLs and token files as sensitive.
- The callback must be the exact localhost loopback URL for the active
  authorization attempt, including its state; never substitute a code-only
  paste.
- Do not use deprecated out-of-band OAuth or invent provider request keys.
- Do not manually delete an existing token as a prerequisite to phone-first
  auth. Replacement must be written only after a successful OAuth exchange.
- Do not call reauthentication complete when only a token was written.
  Completion requires service restart and a fresh feed/readback.
- If the auth command cannot be run interactively, stop and report the
  blocker; do not make a systemd poller perform consent. If the deployed
  source lacks `--auth`, stop for source/installer rollout instead of claiming
  the Pi was updated.

```

## Remaining proof boundary

This repair does not claim that the live skill has been amended, that the
installer has deployed these files, that OAuth consent succeeds for a real
account, or that either systemd service is enabled and refreshing. Those
require the operator's normal deployment and live readback procedure without
collecting or exposing credential values.

The governed proposal above remains the single pending proposal
`ffd8f32c-24c7-4cce-b71d-880fc5cf834d` in human review; the post-submission
oauthlib/PKCE hardening changes the implementation evidence but not the
operator-facing route, so no duplicate proposal was created.
```
