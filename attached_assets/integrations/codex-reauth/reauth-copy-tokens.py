#!/usr/bin/env python3
"""Copy fresh Codex CLI OAuth tokens into every OpenClaw agent's auth profiles.

Ran by the mgmt-bot's /codex_reauth flow right after `codex login --device-auth`
completes. Source of truth: ~/.codex/auth.json (written by the Codex CLI).
Target: ~/.openclaw/agents/*/agent/auth-profiles.json, profile key
"openai-codex:default" with the shape the gateway expects:

    {"type": "oauth", "provider": "openai-codex",
     "access": <jwt>, "refresh": <token>, "expires": <ms epoch>,
     "accountId": <chatgpt account id>}

Exit code 0 = main agent updated (others best-effort, reported in output).
Exit code 1 = hard failure; stdout/stderr explains why (mgmt-bot relays it).
"""

import base64
import json
import pathlib
import subprocess
import sys
import time

HOME = pathlib.Path.home()
CODEX_AUTH = HOME / ".codex" / "auth.json"
AGENTS_DIR = HOME / ".openclaw" / "agents"
PROFILE_KEY = "openai-codex:default"


def fail(msg: str) -> None:
    print(f"ERROR: {msg}")
    sys.exit(1)


def jwt_claims(token: str) -> dict:
    """Decode a JWT payload without verification (we only need exp/account id)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def main() -> None:
    if not CODEX_AUTH.exists():
        fail(f"{CODEX_AUTH} not found — did `codex login` actually complete?")
    try:
        cli = json.loads(CODEX_AUTH.read_text())
    except Exception as e:
        fail(f"could not parse {CODEX_AUTH}: {e}")

    tokens = cli.get("tokens") or {}
    access = tokens.get("access_token") or ""
    refresh = tokens.get("refresh_token") or ""
    if not access or not refresh:
        fail(f"{CODEX_AUTH} has no access_token/refresh_token — sign-in did not complete")

    claims = jwt_claims(access)

    # Expiry: prefer the exp claim baked into the access token (most reliable),
    # fall back to a conservative 50 minutes from now.
    exp = claims.get("exp")
    if isinstance(exp, (int, float)) and exp > time.time():
        expires_ms = int(exp * 1000)
    else:
        expires_ms = int((time.time() + 50 * 60) * 1000)

    account_id = tokens.get("account_id") or ""
    if not account_id:
        auth_claim = claims.get("https://api.openai.com/auth") or {}
        account_id = auth_claim.get("chatgpt_account_id") or ""

    entry_update = {
        "type": "oauth",
        "provider": "openai-codex",
        "access": access,
        "refresh": refresh,
        "expires": expires_ms,
    }
    if account_id:
        entry_update["accountId"] = account_id

    def update_auth_file(auth_file: pathlib.Path) -> str:
        # Some installs chattr +i these files; unlock before writing.
        # -n prevents an interactive sudo password prompt from hanging us.
        try:
            subprocess.run(["sudo", "-n", "chattr", "-i", str(auth_file)],
                           capture_output=True, timeout=10)
        except Exception:
            pass  # best-effort: file is usually not immutable
        data: dict = {}
        if auth_file.exists():
            try:
                data = json.loads(auth_file.read_text())
            except Exception as e:
                return f"ERR  {auth_file}: could not parse ({e})"
            if not isinstance(data, dict):
                return f"ERR  {auth_file}: unexpected format"

        # Two shapes exist in the wild (see knowledge/troubleshooting.md):
        #   A) "profiles" is a DICT of {profileName: credentialObject}
        #   B) "profiles" is a LIST of active profile names, and the credential
        #      objects live as TOP-LEVEL keys next to it.
        profiles = data.get("profiles")
        if isinstance(profiles, list):
            if PROFILE_KEY not in profiles:
                profiles.append(PROFILE_KEY)
            existing = data.get(PROFILE_KEY)
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged.update(entry_update)
            data[PROFILE_KEY] = merged
            shape = "list"
        else:
            if not isinstance(profiles, dict):
                data["profiles"] = {}
            existing = data["profiles"].get(PROFILE_KEY)
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged.update(entry_update)
            data["profiles"][PROFILE_KEY] = merged
            shape = "dict"

        auth_file.parent.mkdir(parents=True, exist_ok=True)
        auth_file.write_text(json.dumps(data, indent=2))
        return f"OK   {auth_file} (profiles shape: {shape})"

    main_auth = AGENTS_DIR / "main" / "agent" / "auth-profiles.json"
    result = update_auth_file(main_auth)
    print(result)
    if not result.startswith("OK"):
        fail("could not update the MAIN agent's auth profiles — aborting")

    for auth_file in sorted(AGENTS_DIR.glob("*/agent/auth-profiles.json")):
        if auth_file == main_auth:
            continue
        try:
            print(update_auth_file(auth_file))
        except Exception as e:
            print(f"ERR  {auth_file}: {e}")

    mins_left = max(0, (expires_ms / 1000 - time.time()) / 60)
    print(f"DONE codex tokens copied (access token valid ~{mins_left:.0f} min; "
          f"accountId {'set' if account_id else 'MISSING'})")


if __name__ == "__main__":
    main()
