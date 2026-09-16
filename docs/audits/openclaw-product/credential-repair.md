# Management-bot Git credential repair

**Status:** source repair prepared; no live deployment, clone, push, credential
inspection, or workflow restart was performed.

## Confirmed defect addressed

`mgmt-bot.py` formerly interpolated `GITHUB_TOKEN` into a clone URL and
temporarily rewrote `origin` with that URL before a push. That put the
credential in child-process arguments and could write it to `.git/config`.

The repaired queue path:

1. retains the existing `https://github.com/` clone allowlist and existing
   queue/confirmation behavior, while narrowing clone input to canonical
   `https://github.com/owner/repo(.git)` URLs with no userinfo, query string,
   fragment, or encoded path separators;
2. passes the clean requested URL to `git clone` and never executes
   `git remote set-url` with a credential;
3. builds a minimal child environment for repository and npm work. It retains
   only `HOME`, `PATH`, locale/timezone, and temporary-directory settings plus
   fixed safe Git/npm config controls; it does not inherit bot credentials,
   arbitrary `GIT_CONFIG_*` overrides, or configured helpers. The developer
   `PATH` remains available for clean local/npm functionality;
4. resolves Git through a validated absolute executable from root-controlled
   Debian paths (`/usr/bin`, `/bin`, `/usr/local/bin`) or immutable system/Nix
   paths (`/nix/store`, `/run/current-system/sw`, `/run/wrappers`). It rejects
   user-writable candidates and fails closed if no supported executable is
   available;
5. gives authenticated Git its own trusted `PATH` and validated
   `GIT_EXEC_PATH`, covering `git-remote-https` and its shell children without
   any `HOME/bin` or project `node_modules/.bin` entry. `GITHUB_TOKEN` is
   supplied only to this narrow Git network environment and only through a
   command-scoped Git credential helper;
6. clones with `--no-checkout`, Git hooks/templates/global config and LFS
   filter pathways disabled, and HTTPS transport restricted. It then scrubs and validates the
   origin with the clean environment before a separate hook-disabled checkout
   receives no token;
7. separates existing pull/rebase behavior into authenticated `git fetch`
   followed by clean-environment merge/rebase. Push/fetch commands retain the
   hook/global-config/filter defenses, use HTTPS-only transport, force the
   standard Git upload/receive programs, clear any remote proxy override, and
   require a scrubbed canonical GitHub HTTPS origin before receiving the token;
8. resets any configured credential helper and installs the GitHub-only helper
   with Git `-c` options for that invocation only. The helper emits credentials
   only for `https://github.com`, and its command text contains no credential
   value;
9. checks clone destinations and repositories before remote operations, and
   removes legacy GitHub URL userinfo and credential query parameters from
   `origin`; and
10. redacts configured credential values, URL userinfo, and common
    token/password query parameters before Git output or queue exceptions are
    sent to Telegram or stderr.

Every Git command also receives command-scoped `core.fsmonitor=false` and an
empty `core.fsmonitorHookVersion`. This prevents a repository-local fsmonitor
hook from being launched while an authenticated fetch or push has the token.

The clean environment suppresses global Git configuration, which would
otherwise remove a normal global `user.name`/`user.email` fallback for commits.
For `git_commit_push` only, the bot first reads the repository-local identity
with includes disabled. A local value wins. For each missing field it performs
an includes-disabled, minimal-environment `git config --global --get` read of
only that identity field, then supplies that field as a command-scoped `-c
user.name` or `-c user.email` value to the local commit. No token, npm command,
or network Git phase receives identity values through its environment, and no
other global configuration is restored.

## Helper packaging verification

The credential helper is a static, in-process constant in
`attached_assets/integrations/mgmt-bot/mgmt-bot.py`, passed through Git's
per-command configuration. It does not require an `askpass` executable,
temporary script, credential file, installer change, or a second deployed
asset. The existing installer links this same bot file, so the helper ships
with the repaired bot path without changing the installer.

## Offline TDD coverage

`attached_assets/integrations/mgmt-bot/test_mgmt_bot_git_credentials.py` is
retrospective regression coverage for this repair; it must not be represented
as a test-first execution. It uses an isolated temporary workspace, mocked Git
subprocesses and Telegram delivery, and fixture-only values. It covers:

- clone command argv excludes the fixture token and a simulated cloned
  `.git/config` contains only the clean origin;
- credential-bearing, query-string, fragment, and encoded-path clone URLs are
  rejected before any subprocess starts, with a credential-free rejection;
- push argv excludes the fixture token, a legacy credential-bearing origin is
  cleaned, and a credential-bearing failure URL is redacted;
- URL-userinfo, token-query, and exact-token diagnostic redaction; and
- static rejection of the prior token-URL interpolation plus presence of the
  self-contained scoped helper.
- fixture `GITHUB_TOKEN`, unrelated `SESSION_SECRET`, and injected
  `GIT_CONFIG_*` values are absent from npm, checkout, local Git, and all
  other repository-code subprocess environments; only clone/fetch/push
  receive the fixture GitHub token and HTTPS transport restriction.

The owning agent ran the four regression tests present at that point after the
repair: the current source produced **4 passes**. A temporary baseline copy
from `HEAD` produced **3 failures and 1 error**, establishing retrospective
regression evidence for the removed behavior. This is not evidence of a
test-first run and must not be described as such. No real credential was used.

The helper test additionally executes only the static helper under `/bin/sh`
with an explicitly constructed fixture-only environment. It verifies that
`get` reads Git's `protocol` and `host` fields, returns credentials only for
`https://github.com`, ignores a path containing a token-like query string, and
emits nothing for a non-GitHub host or a non-`get` operation.

After adding that helper-protocol test, the implementation agent ran the
five-test isolated suite: **5 passes**. The run used only explicitly supplied
synthetic values and no Git network operation.

After adding the adversarial clone-URL regression cases, the targeted isolated
suite ran with **6 passes**. Those cases include raw and percent-encoded
token-like query values, a fragment, URL userinfo, and an encoded path
separator; each is rejected before a subprocess can receive the URL.

After adding the minimal-environment and clean-checkout assertions, the
targeted isolated suite ran with **7 passes**. Compatibility consequence:
repository commands no longer receive arbitrary service environment settings
or user/global npm/Git configuration. They retain the standard execution,
locale, temporary-directory, and home-path variables; GitHub HTTPS Git is the
supported remote form for queue remote operations. This is intentional to
prevent repository code and hooks from reading bot secrets.

The final fsmonitor and identity regression run used **10 tests, all passing**.
The suite asserts both fsmonitor overrides on every mocked Git command
(including clone/fetch/push network phases) and verifies fetch uses the token
environment while the following merge does not. It also creates an isolated
local repository and temporary global Git identity, fakes only the final push,
and proves that `git_commit_push` creates the commit using that identity while
the fake token, unrelated secret, and injected global-config override are
absent from all local/identity subprocess environments. A companion local
identity case verifies local `user.name`/`user.email` suppress the global
fallback. No network Git operation is performed.

The planted-executable regression now runs one real, offline Git subprocess
with a synthetic token and a `HOME/.npm-global/bin/git` impostor. It verifies
that the command uses the validated absolute system/Nix Git, the trusted
network `PATH` excludes the planted directory, and the impostor never runs
(so it cannot observe the token). The targeted isolated suite currently
contains **11 tests, all passing**; it performs no network operation and uses
no real credential.

## Residual risks

- A privileged local process that can inspect another process's environment is
  outside this repair's argv/file exposure boundary; Git still needs the token
  in its inherited environment to authenticate.
- The root-controlled executable check is not a same-user filesystem sandbox.
  It is intended to block user-writable HOME/project PATH planting; a
  same-user process that can rewrite a trusted system/Nix path, replace files
  during execution, or inspect this process's environment is outside this
  boundary.
- The static helper uses Git's shell-helper protocol and therefore depends on
  the normal POSIX shell available to Git on the supported Pi environment.
- Repositories that require a non-GitHub remote, SSH Git transport, custom
  Git hooks/filters, a remote proxy, or user/global npm/Git configuration are
  deliberately incompatible with this queue path and need a separately
  designed, least-privilege integration.
- A global Git identity with config includes is intentionally not honored.
  Set `user.name`/`user.email` directly in the repository or in a plain global
  configuration; the queue will not load include chains to obtain identity.
- Only GitHub HTTPS `origin` URLs are changed. Non-GitHub remotes are neither
  given the GitHub token nor rewritten.
- Source tests cannot prove deployed service version, token validity, remote
  authorization, or a successful external Git operation. Those require a
  separately approved live verification that must not disclose credentials.
