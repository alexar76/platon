#!/usr/bin/env bash
# Stop Platon Docker stack and remove orphan backends.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=platon-docker-lib.sh
source "$ROOT/scripts/platon-docker-lib.sh"

platon_ensure_docker || exit 1
platon_stop_dev_processes
platon_cleanup_containers "$ROOT"
echo "▸ platon stopped"
