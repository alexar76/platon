#!/usr/bin/env bash
# Shared Platon Docker helpers — source from platon-up.sh / connect-ecosystem.sh
# Prevents duplicate backends, orphan uvicorns, and port conflicts.

platon_root() {
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  printf '%s\n' "$here"
}

platon_ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "▸ docker not found — install Docker first" >&2
    return 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "▸ docker daemon not running — start it first" >&2
    return 1
  fi
}

platon_ensure_env_file() {
  local env_file="${PLATON_ENV_FILE:-/root/.hermes/platon.env}"
  if [[ ! -f "$env_file" ]]; then
    echo "▸ missing $env_file — copy from platon.env.example" >&2
    return 1
  fi
}

platon_host_uvicorn_pids() {
  # Container uvicorns appear in host ps/cgroup — count only true host (dev) processes.
  local pid
  for pid in $(pgrep -f 'uvicorn platon\.main:app' 2>/dev/null || true); do
    [[ -n "$pid" ]] || continue
    if [[ -r "/proc/$pid/cgroup" ]] && grep -qE '(docker|containerd|libpod)' "/proc/$pid/cgroup" 2>/dev/null; then
      continue
    fi
    printf '%s\n' "$pid"
  done
}

platon_stop_dev_processes() {
  echo "▸ stopping local dev processes (start.sh leftovers)"

  local pid
  while read -r pid; do
    [[ -n "$pid" ]] || continue
    echo "  kill host uvicorn pid $pid"
    kill "$pid" 2>/dev/null || true
  done < <(platon_host_uvicorn_pids)

  while read -r pid; do
    [[ -n "$pid" ]] || continue
    echo "  kill vite dev pid $pid"
    kill "$pid" 2>/dev/null || true
  done < <(pgrep -f 'vite.*--port 5174' 2>/dev/null || true)

  sleep 1

  # Dev binds :9200 on the host; Docker backend does not publish that port.
  if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ':9200 '; then
    if command -v fuser >/dev/null 2>&1; then
      echo "  free host port 9200"
      fuser -k 9200/tcp 2>/dev/null || true
    fi
  fi
  if command -v fuser >/dev/null 2>&1; then
    fuser -k 5174/tcp 2>/dev/null || true
  fi
}

platon_cleanup_containers() {
  local root="$1"
  echo "▸ cleaning stale Platon Docker resources"

  cd "$root"

  docker compose down --remove-orphans 2>/dev/null || true

  # Named containers from compose (including failed recreates)
  docker rm -f platon-platon-backend platon-platon-frontend 2>/dev/null || true

  # Any container whose name looks like platon compose output
  docker ps -aq --filter 'name=platon-platon' | while read -r id; do
    [[ -n "$id" ]] && docker rm -f "$id" 2>/dev/null || true
  done

  # Old compose projects sometimes leave unnamed duplicates with same image
  docker ps -aq --filter 'ancestor=platon-platon-backend' | while read -r id; do
    [[ -n "$id" ]] && docker rm -f "$id" 2>/dev/null || true
  done
  docker ps -aq --filter 'ancestor=platon-platon-frontend' | while read -r id; do
    [[ -n "$id" ]] && docker rm -f "$id" 2>/dev/null || true
  done

  # Containers still running uvicorn platon.main under random names
  docker ps -q | while read -r id; do
    [[ -n "$id" ]] || continue
    if docker inspect -f '{{.Config.Cmd}}' "$id" 2>/dev/null | grep -q 'platon\.main:app'; then
      echo "  remove orphan backend container $id"
      docker rm -f "$id" 2>/dev/null || true
    fi
  done
}

platon_free_frontend_port() {
  # :8080 should belong to platon-platon-frontend only
  if ! command -v ss >/dev/null 2>&1; then
    return 0
  fi
  if ! ss -ltn 2>/dev/null | grep -q ':8080 '; then
    return 0
  fi

  local holder
  holder="$(docker ps --filter 'publish=8080' --format '{{.Names}}' 2>/dev/null | head -1 || true)"
  if [[ -n "$holder" && "$holder" != "platon-platon-frontend" ]]; then
    echo "▸ port 8080 held by $holder — stopping it"
    docker rm -f "$holder" 2>/dev/null || true
  elif [[ -z "$holder" ]]; then
    echo "▸ warning: port 8080 in use by non-Docker process — check with: ss -ltnp | grep 8080" >&2
  fi
}

platon_compose_up() {
  local root="$1"
  shift
  cd "$root"
  echo "▸ docker compose up $*"
  docker compose up -d "$@"
}

platon_wait_healthy() {
  local url="${1:-http://127.0.0.1:8080/api/health}"
  local attempts="${2:-45}"

  echo "▸ waiting for health ($url)"
  local i
  for i in $(seq 1 "$attempts"); do
    if curl -sf "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

platon_verify_single_backend() {
  local root="$1"
  cd "$root"

  local backend_count host_uvicorns container_workers
  backend_count="$(docker ps --filter 'name=^platon-platon-backend$' --filter 'status=running' -q | wc -l | tr -d ' ')"

  if [[ "$backend_count" != "1" ]]; then
    echo "▸ ERROR: expected exactly 1 running platon-platon-backend, found $backend_count" >&2
    docker ps -a --filter 'name=platon' >&2 || true
    return 1
  fi

  host_uvicorns="$(platon_host_uvicorn_pids | wc -l | tr -d ' ')"
  if [[ "$host_uvicorns" != "0" ]]; then
    echo "▸ ERROR: $host_uvicorns host uvicorn process(es) still running (dev mode on :9200)" >&2
    platon_host_uvicorn_pids | while read -r pid; do
      ps -p "$pid" -o pid,cmd 2>/dev/null || true
    done >&2
    return 1
  fi

  if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ':9200 '; then
    echo "▸ ERROR: host port 9200 still in use — stop ./start.sh or run platon-down first" >&2
    ss -ltnp 2>/dev/null | grep ':9200 ' >&2 || true
    return 1
  fi

  container_workers="$(docker top platon-platon-backend 2>/dev/null | grep -c uvicorn || echo '?')"
  if [[ "$container_workers" != "1" && "$container_workers" != "?" && "$container_workers" != "2" ]]; then
    # header line in docker top can add +1 on some builds
    echo "▸ WARNING: unexpected uvicorn count in container ($container_workers), expected 1" >&2
  fi

  echo "▸ backend OK — containers: $backend_count, host uvicorns: 0, workers in container: $container_workers"
  return 0
}

platon_print_status() {
  local url="${1:-http://127.0.0.1:8080/api/health}"
  if curl -sf "$url" >/dev/null 2>&1; then
    curl -s "$url" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('  tick', d.get('tick'), 'viewers', d.get('viewers'), 'status', d.get('status', 'ok'))
" 2>/dev/null || true
  fi

  if docker ps --filter 'name=^platon-platon-backend$' --format '{{.Names}}' | grep -q .; then
    docker stats --no-stream --format '  {{.Name}} CPU {{.CPUPerc}} MEM {{.MemUsage}}' \
      platon-platon-backend platon-platon-frontend 2>/dev/null || true
  fi
}

platon_docker_prepare() {
  local root="$1"
  platon_ensure_docker
  platon_ensure_env_file
  platon_stop_dev_processes
  platon_free_frontend_port
  platon_cleanup_containers "$root"
}
