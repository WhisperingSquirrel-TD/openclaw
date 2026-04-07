#!/usr/bin/env bash
# Push current main branch to GitHub.
# Uses the GITHUB_TOKEN secret from Replit environment.
set -e

if [ -z "${GITHUB_TOKEN:-}" ]; then
    echo "ERROR: GITHUB_TOKEN is not set."
    echo "Add it as a Replit secret (GITHUB_TOKEN = your GitHub PAT)."
    exit 1
fi

REPO="WhisperingSquirrel-TD/openclaw"

# Set the remote URL using the current token (never stores token in git config)
git remote set-url origin "https://${GITHUB_TOKEN}@github.com/${REPO}.git"

echo "Pushing main → github.com/${REPO}..."
git push origin main

echo "Done."
