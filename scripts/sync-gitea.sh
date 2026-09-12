#!/usr/bin/env bash
# Sync /root/platon with local Gitea (alexar76/platon).
# Credentials: /root/.gitea/credentials (GITEA_URL, GITEA_USER, GITEA_TOKEN)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CRED="${GITEA_CREDENTIALS:-/root/.gitea/credentials}"

if [[ ! -f "$CRED" ]]; then
  echo "Missing $CRED — create it with GITEA_URL, GITEA_USER, GITEA_TOKEN" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$CRED"

: "${GITEA_URL:?GITEA_URL required}"
: "${GITEA_USER:?GITEA_USER required}"
: "${GITEA_TOKEN:?GITEA_TOKEN required}"

REMOTE="http://${GITEA_USER}:${GITEA_TOKEN}@${GITEA_URL#http://}/${GITEA_USER}/platon.git"

cd "$ROOT"
git remote set-url origin "$REMOTE"
git fetch origin
git push origin "$(git branch --show-current)"
echo "Synced $(git branch --show-current) → ${GITEA_URL}/${GITEA_USER}/platon"
