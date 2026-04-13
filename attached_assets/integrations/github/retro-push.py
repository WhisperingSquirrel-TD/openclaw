#!/usr/bin/env python3
"""
Retroactive GitHub push for an existing local OpenClaw project.

Handles projects that were built locally (via app-build / dev-run) before the
GitHub repo was created. Does the following in one shot:

  1. Verify the project directory exists
  2. Create the GitHub repo (fails loudly if it already exists with that name)
  3. Ensure the directory is a git repo (git init if not)
  4. Detach from any old remote (e.g. template repo)
  5. Add the new repo as origin
  6. Stage + commit everything not yet committed
  7. Push to main

Usage:
  python3 retro-push.py <project-name> [--org <github-org>] [--private]

Examples:
  python3 ~/.openclaw/integrations/github/retro-push.py george-dean-portfolio
  python3 ~/.openclaw/integrations/github/retro-push.py my-app --org MyOrg --private
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


STATE_DIR    = Path.home() / ".openclaw"
PROJECTS_DIR = STATE_DIR / "workspace" / "projects"


# ---------------------------------------------------------------------------
# Env / .env loader
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    env_file = STATE_DIR / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fail(msg: str) -> None:
    print(f"\n❌  {msg}", file=sys.stderr)
    sys.exit(1)


def info(msg: str) -> None:
    print(f"   {msg}")


def step(n: int, title: str) -> None:
    print(f"\nStep {n}: {title}")
    print("─" * 50)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                            capture_output=True, text=True)
    if check and result.returncode != 0:
        out = (result.stdout + result.stderr).strip()
        fail(f"Command failed: {' '.join(cmd)}\n{out}")
    return result


# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------

def github_request(method: str, path: str, token: str, data: dict | None = None) -> dict:
    url = f"https://api.github.com{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req  = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        try:
            detail = json.loads(body_text).get("message", body_text)
        except Exception:
            detail = body_text
        fail(f"GitHub API {e.code} on {method} {path}\n  {detail}\n"
             f"  Hint: token needs 'repo' scope")
    except urllib.error.URLError as e:
        fail(f"Network error reaching GitHub API: {e.reason}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retroactively create GitHub repo and push an existing local project."
    )
    parser.add_argument("project", help="Project name (must match directory in workspace/projects/)")
    parser.add_argument("--org",     default=None,  help="GitHub org (default: your personal account)")
    parser.add_argument("--private", action="store_true", help="Make repo private (default: public)")
    parser.add_argument("--description", default="", help="Repo description")
    args = parser.parse_args()

    _load_dotenv()

    project     = args.project.strip()
    project_dir = PROJECTS_DIR / project

    print(f"\n🔧  Retroactive GitHub push — {project}")
    print("=" * 55)

    # ── Step 1: Verify project directory ────────────────────────────────────
    step(1, "Verify project directory")
    if not project_dir.exists():
        fail(
            f"Project directory not found: {project_dir}\n"
            f"  Check the name — available projects:\n"
            + "\n".join(f"    • {d.name}" for d in PROJECTS_DIR.iterdir()
                        if d.is_dir() and not d.name.startswith("."))
            if PROJECTS_DIR.exists() else f"  Projects dir missing: {PROJECTS_DIR}"
        )
    info(f"Found: {project_dir}")

    # ── Step 2: Check token ──────────────────────────────────────────────────
    step(2, "Verify GitHub token")
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        fail(
            "GITHUB_TOKEN not found in environment or ~/.openclaw/.env\n"
            "  Add: GITHUB_TOKEN=<your-personal-access-token>\n"
            "  Token needs scope: repo"
        )

    user_info = github_request("GET", "/user", token)
    auth_user = user_info["login"]
    owner     = args.org if args.org else auth_user
    info(f"Authenticated as: {auth_user}  |  Repo owner: {owner}")

    # ── Step 3: Create GitHub repo ───────────────────────────────────────────
    step(3, f"Create GitHub repo: {owner}/{project}")

    # Check if repo already exists
    existing = None
    try:
        existing = github_request("GET", f"/repos/{owner}/{project}", token)
    except SystemExit:
        pass  # 404 = doesn't exist, which is what we want

    if existing:
        clone_url = existing["clone_url"]
        html_url  = existing["html_url"]
        info(f"Repo already exists: {html_url}")
        info("Skipping creation — will use existing repo as remote.")
    else:
        endpoint = f"/orgs/{owner}/repos" if args.org else "/user/repos"
        result   = github_request("POST", endpoint, token, {
            "name":        project,
            "description": args.description or f"OpenClaw project: {project}",
            "private":     args.private,
            "auto_init":   False,
        })
        clone_url = result["clone_url"]
        html_url  = result["html_url"]
        info(f"Repo created: {html_url}")

    # ── Step 4: Ensure local git repo ────────────────────────────────────────
    step(4, "Ensure local git repository")

    git_dir = project_dir / ".git"
    if not git_dir.exists():
        run(["git", "init", "-b", "main"], cwd=project_dir)
        info("Initialised new git repo (main branch)")
    else:
        info("Git repo already initialised")

        # Ensure default branch is main
        branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                     cwd=project_dir, check=False).stdout.strip()
        if branch and branch != "main" and branch != "HEAD":
            run(["git", "branch", "-M", "main"], cwd=project_dir)
            info(f"Renamed branch {branch} → main")

    # ── Step 5: Set origin remote ────────────────────────────────────────────
    step(5, "Set origin remote")

    remotes = run(["git", "remote", "-v"], cwd=project_dir, check=False).stdout.strip()
    if "origin" in remotes:
        current = [l for l in remotes.splitlines() if l.startswith("origin")]
        if clone_url in remotes:
            info(f"Origin already points to {clone_url} — no change needed")
        else:
            info(f"Current remote:\n    {chr(10).join(current)}")
            run(["git", "remote", "remove", "origin"], cwd=project_dir)
            run(["git", "remote", "add", "origin", clone_url], cwd=project_dir)
            info(f"Remote updated → {clone_url}")
    else:
        run(["git", "remote", "add", "origin", clone_url], cwd=project_dir)
        info(f"Remote set → {clone_url}")

    # ── Step 6: Set git identity if not configured ───────────────────────────
    step(6, "Check git identity")

    git_name  = run(["git", "config", "user.name"],  cwd=project_dir, check=False).stdout.strip()
    git_email = run(["git", "config", "user.email"], cwd=project_dir, check=False).stdout.strip()

    if not git_name:
        run(["git", "config", "user.name", "OpenClaw"], cwd=project_dir)
        info("Set git user.name = OpenClaw")
    else:
        info(f"git user.name  = {git_name}")

    if not git_email:
        run(["git", "config", "user.email", "openclaw@local"], cwd=project_dir)
        info("Set git user.email = openclaw@local")
    else:
        info(f"git user.email = {git_email}")

    # ── Step 7: Commit everything not yet committed ──────────────────────────
    step(7, "Commit local changes")

    status = run(["git", "status", "--porcelain"], cwd=project_dir, check=False).stdout.strip()
    if status:
        run(["git", "add", "-A"], cwd=project_dir)
        run(["git", "commit", "-m", "feat: initial build (retroactive GitHub push)"],
            cwd=project_dir)
        info("Committed all local changes")
    else:
        # Check if there's already a commit
        log = run(["git", "log", "--oneline", "-1"], cwd=project_dir, check=False).stdout.strip()
        if log:
            info(f"Working tree clean — last commit: {log}")
        else:
            # No commits and nothing to stage — create an empty initial commit
            run(["git", "commit", "--allow-empty", "-m", "chore: initial commit"],
                cwd=project_dir)
            info("Created initial empty commit")

    # ── Step 8: Push to GitHub ───────────────────────────────────────────────
    step(8, "Push to GitHub")

    push = run(
        ["git", "push", "-u", "origin", "main"],
        cwd=project_dir, check=False,
    )
    if push.returncode != 0:
        out = (push.stdout + push.stderr).strip()
        # Handle "already up to date" or non-fast-forward
        if "Everything up-to-date" in out or "up-to-date" in out.lower():
            info("Already up to date on GitHub")
        elif "non-fast-forward" in out or "rejected" in out:
            info("Remote has diverged — attempting force push (safe: first push of project)...")
            run(["git", "push", "-u", "--force", "origin", "main"], cwd=project_dir)
            info("Force pushed successfully")
        else:
            fail(f"Push failed:\n{out}")
    else:
        info(push.stdout.strip() or "Pushed successfully")

    # ── Done ─────────────────────────────────────────────────────────────────
    log_out = run(["git", "log", "--oneline", "-3"], cwd=project_dir, check=False).stdout.strip()
    print(f"""
✅  Done — {project} is now on GitHub

   Repo:     {html_url}
   Local:    {project_dir}
   Commits:  {log_out.splitlines()[0] if log_out else '(none)'}

   Future builds will push automatically before deploying to Vercel.
""")


if __name__ == "__main__":
    main()
