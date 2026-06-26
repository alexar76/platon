#!/usr/bin/env bash
# Safe Platon Docker deploy — one backend, no orphan uvicorns, no CPU runaway.
#
# Usage:
#   ./scripts/platon-up.sh              # full stack (backend + frontend)
#   ./scripts/platon-up.sh --backend    # backend only (ecosystem hook)
#   ./scripts/platon-up.sh --no-build   # restart without rebuild
#   ./scripts/platon-down.sh            # clean shutdown
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=platon-docker-lib.sh
source "$ROOT/scripts/platon-docker-lib.sh"

SERVICES=(platon-backend platon-frontend)
BUILD=1

usage() {
  sed -n '2,8p' "$0" | tr -d '#'
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend|--backend-only)
      SERVICES=(platon-backend)
      shift
      ;;
    --no-build)
      BUILD=0
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "unknown option: $1 (try --help)" >&2
      exit 1
      ;;
  esac
done

platon_docker_prepare "$ROOT"

UP_ARGS=(--remove-orphans "${SERVICES[@]}")
if [[ "$BUILD" -eq 1 ]]; then
  UP_ARGS=(--build "${UP_ARGS[@]}")
fi

platon_compose_up "$ROOT" "${UP_ARGS[@]}"

if ! platon_wait_healthy "http://127.0.0.1:8080/api/health" 45; then
  if [[ " ${SERVICES[*]} " == *" platon-frontend "* ]]; then
    echo "▸ health check timed out — logs:" >&2
    docker compose -f "$ROOT/docker-compose.yml" logs --tail 40 platon-backend platon-frontend >&2 || true
    exit 1
  fi
  # backend-only: frontend may be down; check backend directly in container
  if ! docker exec platon-platon-backend python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9200/api/health', timeout=3)" \
    >/dev/null 2>&1; then
    echo "▸ backend health check timed out — check: docker compose logs platon-backend" >&2
    exit 1
  fi
fi

platon_verify_single_backend "$ROOT"
echo "▸ platon healthy"
platon_print_status
