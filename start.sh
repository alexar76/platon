#!/usr/bin/env bash
# Local dev ONLY — production deploy: ./scripts/platon-up.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [[ "${1:-}" == "--docker" ]]; then
  shift
  exec "$ROOT/scripts/platon-up.sh" "$@"
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^platon-platon-backend$'; then
  echo "▸ platon docker backend is running — use ./scripts/platon-up.sh (or ./start.sh --docker)" >&2
  exit 1
fi

if pgrep -f 'uvicorn platon\.main:app' >/dev/null 2>&1; then
  # shellcheck source=scripts/platon-docker-lib.sh
  source "$ROOT/scripts/platon-docker-lib.sh"
  if [[ -n "$(platon_host_uvicorn_pids)" ]]; then
    echo "▸ host uvicorn platon.main already running — stop it first or use ./scripts/platon-up.sh" >&2
    exit 1
  fi
fi

if ss -ltn 2>/dev/null | grep -q ':9200 '; then
  echo "▸ port 9200 already in use" >&2
  exit 1
fi

echo "▸ Platon UMBRAL — starting backend :9200 + frontend :5174"
cd "$ROOT/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -e ".[dev]" -q
fi
export PLATON_PUBLIC_URL="${PLATON_PUBLIC_URL:-http://localhost:9200}"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
.venv/bin/python -m uvicorn platon.main:app --host 0.0.0.0 --port 9200 --workers 1 &
BACK_PID=$!

cd "$ROOT/frontend"
npm install -q
npm run dev -- --host 0.0.0.0 --port 5174 &
FRONT_PID=$!

trap 'kill $BACK_PID $FRONT_PID 2>/dev/null' EXIT
echo "▸ Open http://localhost:5174"
wait
