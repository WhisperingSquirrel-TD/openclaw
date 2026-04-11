#!/usr/bin/env python3
"""
GitHub repo creation helper for OpenClaw app development workflow.

Usage:
  python3 create-repo.py --name <repo-name> [options]

Called by the app-init skill. Uses GITHUB_TOKEN from environment / .env file.
Fails loudly on any error — never continues silently.
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from typing import Dict, Optional


def load_env_file(path: str) -> None:
    """Load key=value pairs from a .env file into os.environ (does not overwrite existing)."""
    if not os.path.isfile(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def github_request(
    method: str,
    path: str,
    token: str,
    data: Optional[Dict] = None,
) -> dict:
    url = f"https://api.github.com{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        try:
            detail = json.loads(body_text).get("message", body_text)
        except Exception:
            detail = body_text
        fail(
            f"GitHub API {e.code} on {method} {path}\n"
            f"  Message: {detail}\n"
            f"  Hint: check token scope (needs 'repo' or 'public_repo')"
        )
    except urllib.error.URLError as e:
        fail(f"Network error reaching GitHub API: {e.reason}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a GitHub repo for an OpenClaw app project."
    )
    parser.add_argument("--name", required=True, help="Repository name (e.g. my-project)")
    parser.add_argument(
        "--template",
        default=None,
        help="Template repo in owner/name format (e.g. tomsmith/openclaw-template)",
    )
    parser.add_argument(
        "--private",
        default="false",
        choices=["true", "false"],
        help="Make repo private (default: false)",
    )
    parser.add_argument(
        "--org",
        default=None,
        help="GitHub org to create repo under (default: authenticated user)",
    )
    parser.add_argument(
        "--description",
        default="",
        help="Repo description",
    )
    args = parser.parse_args()

    # Load .env from standard OpenClaw location
    env_path = os.path.expanduser("~/.openclaw/.env")
    load_env_file(env_path)

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        fail(
            "GITHUB_TOKEN not found in environment or ~/.openclaw/.env\n"
            "  Fix: add GITHUB_TOKEN=<your-token> to ~/.openclaw/.env\n"
            "  Token needs scopes: repo (or public_repo for public repos)"
        )

    repo_name = args.name.strip()
    if not repo_name:
        fail("--name cannot be empty")

    is_private = args.private == "true"

    # Resolve the authenticated user
    print("Verifying GitHub token...")
    user_info = github_request("GET", "/user", token)
    authenticated_user = user_info["login"]
    print(f"Authenticated as: {authenticated_user}")

    owner = args.org if args.org else authenticated_user

    # Create from template if specified
    if args.template:
        template_owner, _, template_repo = args.template.partition("/")
        if not template_repo:
            fail(f"--template must be in owner/name format, got: {args.template}")

        print(f"Creating repo '{owner}/{repo_name}' from template '{args.template}'...")
        data = {
            "owner": owner,
            "name": repo_name,
            "description": args.description,
            "private": is_private,
            "include_all_branches": False,
        }
        result = github_request(
            "POST",
            f"/repos/{template_owner}/{template_repo}/generate",
            token,
            data,
        )
    else:
        print(f"Creating blank repo '{owner}/{repo_name}'...")
        endpoint = f"/orgs/{owner}/repos" if args.org else "/user/repos"
        data = {
            "name": repo_name,
            "description": args.description,
            "private": is_private,
            "auto_init": True,
            "gitignore_template": "Node",
        }
        result = github_request("POST", endpoint, token, data)

    clone_url = result.get("clone_url", "")
    html_url = result.get("html_url", "")

    if not clone_url:
        fail(f"Repo created but clone_url missing from response: {result}")

    print()
    print(f"Repo created successfully.")
    print(f"  Name:      {owner}/{repo_name}")
    print(f"  URL:       {html_url}")
    print(f"  Clone URL: {clone_url}")
    print(f"  Private:   {is_private}")
    print()
    print(clone_url)  # Final line is the clone URL for scripted use


if __name__ == "__main__":
    main()
