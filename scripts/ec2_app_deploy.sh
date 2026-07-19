#!/usr/bin/env bash
# Deploy relocation-jobs panel to EC2 (same host as Postgres + Redis).
#
# Usage:
#   ./scripts/ec2_app_deploy.sh sync              # rsync repo to EC2
#   ./scripts/ec2_app_deploy.sh deploy            # sync + build (if needed) + run
#   ./scripts/ec2_app_deploy.sh deploy --force    # rebuild both images even if hashes match
#   ./scripts/ec2_app_deploy.sh prune             # free dangling images + trim builder cache
#   ./scripts/ec2_app_deploy.sh open-sg           # open HTTP/HTTPS on security group (manual)
#   ./scripts/ec2_app_deploy.sh status            # container + health check
#   ./scripts/ec2_app_deploy.sh worker-logs       # tail fetch scheduler logs
#
# Requires: aws-postgres.env, SSH key at ~/Downloads/relocation.pem
# Disk: 8G root fills from leftover panel/worker images; deploy prunes dangling
# images only. BuildKit cache is kept across deploys so tectonic/pip/playwright
# layers are reused — never wiped mid/post-deploy (use `prune` for that).
#
# Escape hatches:
#   FORCE_REBUILD=1   — same as deploy --force
#   FORCE_FRONTEND=1  — rebuild frontend even if board.js is fresh
#   FORCE_HOMEPAGE=1  — rebuild homepage even if static export is fresh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_FILE="$ROOT/aws-postgres.env"
REMOTE_DIR=/home/ec2-user/relocation-jobs
HASH_FILE=.deploy-hashes
REGION="${AWS_REGION:-eu-central-1}"
EC2_SSH_USER="${EC2_SSH_USER:-ec2-user}"
EC2_SSH_KEY="${EC2_SSH_KEY:-$HOME/Downloads/relocation.pem}"
PANEL_IMAGE=relocation-panel:ec2
PANEL_CONTAINER=relocation-panel
MCP_CONTAINER=relocation-mcp
WORKER_IMAGE=relocation-fetch-worker:ec2
WORKER_CONTAINER=relocation-fetch-worker
CADDY_CONTAINER=relocation-caddy
PANEL_PORT=10000
MCP_PORT=10001
MCP_PUBLIC_BASE_URL="${MCP_PUBLIC_BASE_URL:-https://mcp.kuchup.com}"
FORCE_REBUILD="${FORCE_REBUILD:-0}"

log() { printf '[ec2-app] %s\n' "$*"; }
die() { printf '[ec2-app] ERROR: %s\n' "$*" >&2; exit 1; }

load_state() {
  [[ -f "$STATE_FILE" ]] || die "Missing $STATE_FILE"
  # shellcheck disable=SC1090
  source "$STATE_FILE"
  [[ -n "${ELASTIC_IP:-}" ]] || die "ELASTIC_IP missing in $STATE_FILE"
  [[ -n "${DB_PASSWORD:-}" ]] || die "DB_PASSWORD missing in $STATE_FILE"
}

ssh_cmd() {
  local key_args=()
  [[ -f "$EC2_SSH_KEY" ]] && key_args=(-i "$EC2_SSH_KEY")
  ssh "${key_args[@]}" -o StrictHostKeyChecking=accept-new "${EC2_SSH_USER}@${ELASTIC_IP}" "$@"
}

rsync_cmd() {
  local key_args=()
  [[ -f "$EC2_SSH_KEY" ]] && key_args=(-e "ssh -i ${EC2_SSH_KEY} -o StrictHostKeyChecking=accept-new")
  rsync -az --delete \
    --exclude '.git/' \
    --exclude '.venv/' \
    --exclude 'node_modules/' \
    --exclude 'frontend/node_modules/' \
    --exclude 'homepage/node_modules/' \
    --exclude 'homepage/.next/' \
    --exclude 'homepage/out/' \
    --exclude '.entire/' \
    --exclude 'data/' \
    --exclude '/dist/' \
    --exclude '__pycache__/' \
    --exclude '.env' \
    --exclude 'aws-postgres.env' \
    --exclude '.pytest_cache/' \
    --exclude '*.pyc' \
    --exclude '.deploy-hashes' \
    "${key_args[@]}" \
    "$ROOT/" "${EC2_SSH_USER}@${ELASTIC_IP}:${REMOTE_DIR}/"
}

redis_password() {
  if [[ -n "${REDIS_PASSWORD:-}" ]]; then
    printf '%s' "$REDIS_PASSWORD"
    return
  fi
  if [[ -f "$ROOT/.env" ]]; then
    local url
    url="$(grep -E '^REDIS_URL=' "$ROOT/.env" | cut -d= -f2- || true)"
    if [[ "$url" =~ redis://:([^@]+)@ ]]; then
      printf '%s' "${BASH_REMATCH[1]}"
      return
    fi
  fi
  die "Set REDIS_PASSWORD or REDIS_URL in .env"
}

panel_secret() {
  if [[ -f "$ROOT/.env" ]]; then
    local key
    key="$(grep -E '^PANEL_SECRET_KEY=' "$ROOT/.env" | cut -d= -f2- || true)"
    if [[ -n "$key" && "$key" != "change-me-to-a-long-random-string" ]]; then
      printf '%s' "$key"
      return
    fi
  fi
  openssl rand -hex 32
}

admin_password() {
  if [[ -f "$ROOT/.env" ]]; then
    local pass
    pass="$(grep -E '^PANEL_ADMIN_PASSWORD=' "$ROOT/.env" | cut -d= -f2- || true)"
    if [[ -n "$pass" && "$pass" != "change-me" ]]; then
      printf '%s' "$pass"
      return
    fi
  fi
  printf '%s' "${PANEL_ADMIN_PASSWORD:-change-me}"
}

# True when any path under $1 is newer than file $2, or $2 is missing.
_sources_newer_than() {
  local src_root="$1"
  local output="$2"
  [[ -e "$output" ]] || return 0
  # -prune skips heavy dirs; find -newer returns 0 if any match.
  find "$src_root" \
    \( -name node_modules -o -name .next -o -name out -o -name __pycache__ \) -prune \
    -o -type f -newer "$output" -print -quit | grep -q .
}

maybe_build_frontend() {
  [[ -d "$ROOT/frontend" ]] || return 0
  local out="$ROOT/relocation_jobs/static/dist/board.js"
  if [[ "${FORCE_FRONTEND:-0}" == "1" ]] || _sources_newer_than "$ROOT/frontend" "$out"; then
    log "Building frontend (board.js)..."
    (cd "$ROOT/frontend" && npm run build --silent)
  else
    log "Frontend up to date — skipping npm build"
  fi
}

maybe_build_homepage() {
  [[ -d "$ROOT/homepage" ]] || return 0
  local out="$ROOT/relocation_jobs/static/homepage/index.html"
  local need=0
  if [[ "${FORCE_HOMEPAGE:-0}" == "1" ]]; then
    need=1
  elif _sources_newer_than "$ROOT/homepage" "$out"; then
    need=1
  elif [[ -f "$ROOT/scripts/export_homepage_countries.py" ]] \
    && [[ "$ROOT/scripts/export_homepage_countries.py" -nt "$out" ]]; then
    need=1
  fi
  if [[ "$need" -eq 1 ]]; then
    log "Building homepage (static export)..."
    "$ROOT/scripts/build_homepage.sh"
  else
    log "Homepage up to date — skipping static export"
  fi
}

cmd_sync() {
  load_state
  maybe_build_frontend
  maybe_build_homepage
  log "Syncing to ${EC2_SSH_USER}@${ELASTIC_IP}:${REMOTE_DIR}"
  ssh_cmd "mkdir -p ${REMOTE_DIR}"
  rsync_cmd
  log "Sync OK"
}

cmd_open_sg() {
  load_state
  command -v aws >/dev/null 2>&1 || die "aws CLI required"
  local sg="${SECURITY_GROUP_ID:-}"
  if [[ -z "$sg" && -n "${EC2_INSTANCE_ID:-}" ]]; then
    sg="$(aws ec2 describe-instances --region "$REGION" --instance-ids "$EC2_INSTANCE_ID" \
      --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId' --output text)"
  fi
  [[ -n "$sg" ]] || die "Could not resolve security group"
  for port in 80 443; do
    aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$sg" \
      --ip-permissions "IpProtocol=tcp,FromPort=${port},ToPort=${port},IpRanges=[{CidrIp=0.0.0.0/0,Description=panel-http}]" \
      2>/dev/null || log "Port ${port} may already be open"
  done
  log "Security group ${sg}: TCP 80/443 open"
}

# Docker disk reclaim — NEVER touch volumes or the Postgres/Redis containers.
#
# Data lives in named volumes (`pgdata`, redis data), not in images. Safe ops:
#   docker image prune -f     # dangling (<none>) images only
#   docker builder prune -af  # build cache only (manual prune)
# Forbidden in this script (would risk DB wipe):
#   docker volume prune / docker volume rm
#   docker system prune --volumes
#   docker rm -v pg
#   any prune that stops or removes container `pg`
#
# Deploy never wipes BuildKit cache — that is what forces tectonic/pip/playwright
# re-downloads on every deploy. Manual `prune` may reclaim builder cache when
# disk is tight (keeps ~8G of recent cache so the next deploy is not cold).
remote_docker_prune() {
  local builder="${1:-}"
  local label="${2:-}"
  [[ -n "$label" ]] && log "Docker prune (${label})..."
  ssh_cmd bash -s -- "$builder" <<'SCRIPT'
set -euo pipefail
builder_arg="${1:-}"

assert_db_safe() {
  local phase="$1"
  if ! docker inspect -f '{{.State.Running}}' pg 2>/dev/null | grep -qx true; then
    echo "[ec2-app] ERROR: Postgres container 'pg' is not running (${phase}) — refusing prune" >&2
    exit 1
  fi
  if ! docker volume inspect pgdata >/dev/null 2>&1; then
    echo "[ec2-app] ERROR: Docker volume 'pgdata' missing (${phase}) — refusing prune" >&2
    exit 1
  fi
}

assert_db_safe "before prune"
printf '[ec2-app] disk before prune: '
df -h / | awk 'NR==2 {print $3 " used / " $2 " (" $5 ")"}'

# Dangling images only — never -a (unused), volumes, containers.
docker image prune -f
# Manual prune only: trim builder cache but keep recent layers warm.
if [ "$builder_arg" = "builder" ]; then
  docker builder prune -af --keep-storage 8GB >/dev/null
fi

assert_db_safe "after prune"
printf '[ec2-app] disk after prune:  '
df -h / | awk 'NR==2 {print $3 " used / " $2 " (" $5 ")"}'
printf '[ec2-app] db guard: pg running, volume pgdata present\n'
SCRIPT
}

cmd_prune() {
  load_state
  remote_docker_prune "builder" "manual"
}

# Compute a content hash of image inputs on the remote tree (after rsync).
# Paths are relative to REMOTE_DIR. Static assets are bind-mounted into the
# panel at runtime, so they are omitted — changing CSS/homepage alone should
# not force a Python image rebuild.
remote_image_hash() {
  local kind="$1"
  ssh_cmd bash -s -- "$REMOTE_DIR" "$kind" <<'SCRIPT'
set -euo pipefail
cd "$1"
kind="$2"
tmp="$(mktemp)"
cleanup() { rm -f "$tmp"; }
trap cleanup EXIT

list_paths() {
  case "$kind" in
    panel)
      printf '%s\n' \
        Dockerfile.ec2 \
        requirements.txt \
        deploy/ec2/tectonic-warm.tex \
        docker-entrypoint.sh \
        scripts/mcp_http_server.py
      [[ -f docker-entrypoint-mcp.sh ]] && printf '%s\n' docker-entrypoint-mcp.sh
      find relocation_jobs \
        \( -path 'relocation_jobs/static' -o -path 'relocation_jobs/static/*' \
           -o -name '__pycache__' -o -name '*.pyc' \) -prune \
        -o -type f -print
      ;;
    worker)
      printf '%s\n' \
        Dockerfile.ec2-worker \
        requirements.txt \
        requirements-playwright.txt \
        scripts/fetch_scheduler_worker.py
      find relocation_jobs \
        \( -path 'relocation_jobs/static' -o -path 'relocation_jobs/static/*' \
           -o -name '__pycache__' -o -name '*.pyc' \) -prune \
        -o -type f -print
      ;;
    *)
      echo "unknown hash kind: $kind" >&2
      exit 1
      ;;
  esac
}

list_paths | LC_ALL=C sort -u | while IFS= read -r path; do
  [[ -e "$path" ]] || continue
  # path + content; stable across machines
  printf '%s\0' "$path"
  cat "$path"
done | sha256sum | awk '{print $1}'
SCRIPT
}

remote_saved_hash() {
  local kind="$1"
  ssh_cmd bash -s -- "$REMOTE_DIR" "$HASH_FILE" "$kind" <<'SCRIPT'
set -euo pipefail
cd "$1"
hash_file="$2"
kind="$3"
[[ -f "$hash_file" ]] || exit 0
awk -F= -v k="$kind" '$1 == k { print $2; exit }' "$hash_file"
SCRIPT
}

remote_save_hash() {
  local kind="$1"
  local digest="$2"
  ssh_cmd bash -s -- "$REMOTE_DIR" "$HASH_FILE" "$kind" "$digest" <<'SCRIPT'
set -euo pipefail
cd "$1"
hash_file="$2"
kind="$3"
digest="$4"
tmp="$(mktemp)"
if [[ -f "$hash_file" ]]; then
  grep -v "^${kind}=" "$hash_file" >"$tmp" || true
fi
printf '%s=%s\n' "$kind" "$digest" >>"$tmp"
mv "$tmp" "$hash_file"
SCRIPT
}

# Returns 0 if a docker build is needed. $3 is the precomputed input digest.
image_needs_rebuild() {
  local kind="$1"
  local image="$2"
  local current="$3"
  if [[ "$FORCE_REBUILD" == "1" ]]; then
    log "${kind}: FORCE_REBUILD — rebuilding"
    return 0
  fi
  if ! ssh_cmd "docker image inspect ${image} >/dev/null 2>&1"; then
    log "${kind}: image ${image} missing — rebuilding"
    return 0
  fi
  local saved
  saved="$(remote_saved_hash "$kind")"
  if [[ -n "$saved" && "$saved" == "$current" ]]; then
    log "${kind}: inputs unchanged (${current:0:12}…) — skipping docker build"
    return 1
  fi
  log "${kind}: inputs changed — rebuilding"
  return 0
}

cmd_deploy() {
  load_state
  local redis_pass db_url redis_url secret admin_pass
  local panel_hash worker_hash
  redis_pass="$(redis_password)"
  secret="$(panel_secret)"
  admin_pass="$(admin_password)"
  db_url="postgresql://${DB_USER:-relocation}:${DB_PASSWORD}@172.17.0.1:5432/${DB_NAME:-relocation_jobs}?sslmode=prefer"
  redis_url="redis://:${redis_pass}@172.17.0.1:6379/0"

  cmd_sync
  # Free leftover dangling images once before builds. Never wipe BuildKit cache.
  remote_docker_prune "" "before builds"

  panel_hash="$(remote_image_hash panel)"
  if image_needs_rebuild panel "$PANEL_IMAGE" "$panel_hash"; then
    log "Building ${PANEL_IMAGE} on EC2 (arm64)..."
    ssh_cmd bash -s <<EOF
set -euo pipefail
cd ${REMOTE_DIR}
cache_args=()
if docker image inspect ${PANEL_IMAGE} >/dev/null 2>&1; then
  cache_args=(--cache-from ${PANEL_IMAGE})
fi
DOCKER_BUILDKIT=1 docker build \\
  --build-arg BUILDKIT_INLINE_CACHE=1 \\
  "\${cache_args[@]}" \\
  -f Dockerfile.ec2 -t ${PANEL_IMAGE} .
EOF
  fi
  remote_save_hash panel "$panel_hash"

  log "Starting panel container..."
  ssh_cmd bash -s <<EOF
set -euo pipefail
docker rm -f ${PANEL_CONTAINER} 2>/dev/null || true
docker run -d --name ${PANEL_CONTAINER} --restart unless-stopped \\
  -p ${PANEL_PORT}:${PANEL_PORT} \\
  -v ${REMOTE_DIR}/relocation_jobs/static:/app/relocation_jobs/static:ro \\
  -e PORT=${PANEL_PORT} \\
  -e PANEL_SCRAPE_ENABLED=0 \\
  -e PANEL_COMPANY_FETCH_ENABLED=1 \\
  -e PANEL_DATA_DIR=/tmp/panel-data \\
  -e PANEL_SECRET_KEY='${secret}' \\
  -e PANEL_ADMIN_USER=admin \\
  -e PANEL_ADMIN_PASSWORD='${admin_pass}' \\
  -e PANEL_ALLOW_REGISTER=0 \\
  -e FETCH_SCHEDULE_ENABLED=1 \\
  -e FETCH_SCHEDULE_INTERVAL_HOURS=6 \\
  -e FETCH_SCHEDULE_CONCURRENCY=4 \\
  -e DATABASE_URL='${db_url}' \\
  -e REDIS_URL='${redis_url}' \\
  -e MCP_PUBLIC_BASE_URL='${MCP_PUBLIC_BASE_URL}' \\
  ${PANEL_IMAGE}
EOF

  log "Starting MCP container..."
  ssh_cmd bash -s <<EOF
set -euo pipefail
docker rm -f ${MCP_CONTAINER} 2>/dev/null || true
docker run -d --name ${MCP_CONTAINER} --restart unless-stopped \\
  -p ${MCP_PORT}:${MCP_PORT} \\
  --entrypoint ./docker-entrypoint-mcp.sh \\
  -e MCP_HTTP_HOST=0.0.0.0 \\
  -e MCP_HTTP_PORT=${MCP_PORT} \\
  -e MCP_PUBLIC_BASE_URL='${MCP_PUBLIC_BASE_URL}' \\
  -e DATABASE_URL='${db_url}' \\
  -e REDIS_URL='${redis_url}' \\
  ${PANEL_IMAGE}
EOF

  worker_hash="$(remote_image_hash worker)"
  if image_needs_rebuild worker "$WORKER_IMAGE" "$worker_hash"; then
    log "Building ${WORKER_IMAGE} on EC2 (Playwright)..."
    ssh_cmd bash -s <<EOF
set -euo pipefail
cd ${REMOTE_DIR}
cache_args=()
if docker image inspect ${WORKER_IMAGE} >/dev/null 2>&1; then
  cache_args=(--cache-from ${WORKER_IMAGE})
fi
DOCKER_BUILDKIT=1 docker build \\
  --build-arg BUILDKIT_INLINE_CACHE=1 \\
  "\${cache_args[@]}" \\
  -f Dockerfile.ec2-worker -t ${WORKER_IMAGE} .
EOF
  fi
  remote_save_hash worker "$worker_hash"

  log "Starting fetch worker container..."
  ssh_cmd bash -s <<EOF
set -euo pipefail
docker rm -f ${WORKER_CONTAINER} 2>/dev/null || true
docker run -d --name ${WORKER_CONTAINER} --restart unless-stopped \\
  -e PANEL_SCRAPE_ENABLED=1 \\
  -e FETCH_SCHEDULE_ENABLED=1 \\
  -e FETCH_SCHEDULE_INTERVAL_HOURS=6 \\
  -e FETCH_SCHEDULE_CONCURRENCY=4 \\
  -e FETCH_COMPANY_TIMEOUT_SECONDS=300 \\
  -e FETCH_COUNTRY_TIMEOUT_SECONDS=2700 \\
  -e PLAYWRIGHT_BOARD_TIMEOUT_SECONDS=90 \\
  -e PANEL_ADMIN_USER=admin \\
  -e PANEL_ADMIN_PASSWORD='${admin_pass}' \\
  -e DATABASE_URL='${db_url}' \\
  ${WORKER_IMAGE}
EOF

  log "Starting Caddy reverse proxy..."
  ssh_cmd bash -s <<EOF
set -euo pipefail
docker rm -f ${CADDY_CONTAINER} 2>/dev/null || true
docker run -d --name ${CADDY_CONTAINER} --restart unless-stopped \\
  -p 80:80 -p 443:443 \\
  --add-host=host.docker.internal:host-gateway \\
  -v ${REMOTE_DIR}/deploy/ec2/Caddyfile:/etc/caddy/Caddyfile:ro \\
  -v relocation_caddy_data:/data \\
  -v relocation_caddy_config:/config \\
  caddy:2-alpine
EOF

  # Dangling images only — keep BuildKit cache for the next deploy.
  remote_docker_prune "" "after deploy"
  # open-sg is intentional/manual — do not reopen 0.0.0.0/0 on every deploy.
  cmd_status
}

cmd_status() {
  load_state
  local domain="${PANEL_DOMAIN:-kuchup.com}"
  local panel_code domain_code ip_code mcp_code mcp_domain_code

  ssh_cmd "docker ps --filter name=relocation- --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
  log "Fetch worker logs (last 20 lines):"
  ssh_cmd "docker logs ${WORKER_CONTAINER} --tail 20 2>&1" || log "  worker not running"

  log "Panel health (localhost:${PANEL_PORT} on EC2):"
  panel_code="$(ssh_cmd "curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:${PANEL_PORT}/api/auth/status" 2>/dev/null || echo 000)"
  if [[ "$panel_code" == "200" ]]; then
    log "  http://127.0.0.1:${PANEL_PORT}/api/auth/status -> ${panel_code} (OK)"
  else
    log "  http://127.0.0.1:${PANEL_PORT}/api/auth/status -> ${panel_code} (FAILED)"
  fi

  log "MCP health (localhost:${MCP_PORT} on EC2):"
  mcp_code="$(ssh_cmd "curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:${MCP_PORT}/healthz" 2>/dev/null || echo 000)"
  if [[ "$mcp_code" == "200" ]]; then
    log "  http://127.0.0.1:${MCP_PORT}/healthz -> ${mcp_code} (OK)"
  else
    log "  http://127.0.0.1:${MCP_PORT}/healthz -> ${mcp_code} (FAILED)"
  fi

  log "Panel health (via domain):"
  domain_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "https://${domain}/api/auth/status" 2>/dev/null || echo 000)"
  if [[ "$domain_code" == "200" ]]; then
    log "  https://${domain}/api/auth/status -> ${domain_code} (OK)"
  else
    log "  https://${domain}/api/auth/status -> ${domain_code} (check DNS/TLS if deploy just finished)"
  fi

  log "MCP health (via domain):"
  mcp_domain_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "https://mcp.kuchup.com/healthz" 2>/dev/null || echo 000)"
  if [[ "$mcp_domain_code" == "200" ]]; then
    log "  https://mcp.kuchup.com/healthz -> ${mcp_domain_code} (OK)"
  else
    log "  https://mcp.kuchup.com/healthz -> ${mcp_domain_code} (check DNS/TLS if deploy just finished)"
  fi

  log "Origin lock-down (Elastic IP, expect 404):"
  ip_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://${ELASTIC_IP}/api/auth/status" 2>/dev/null || echo 000)"
  log "  http://${ELASTIC_IP}/api/auth/status -> ${ip_code}"
}

# Parse global flags then dispatch (--force may appear anywhere).
ACTION=deploy
TAIL_N=100
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      FORCE_REBUILD=1
      shift
      ;;
    sync|deploy|prune|open-sg|status|worker-logs)
      ACTION="$1"
      shift
      ;;
    *)
      if [[ "$ACTION" == "worker-logs" && "$1" =~ ^[0-9]+$ ]]; then
        TAIL_N="$1"
        shift
      else
        die "Usage: $0 {sync|deploy|prune|open-sg|status|worker-logs} [--force]"
      fi
      ;;
  esac
done

case "$ACTION" in
  sync) cmd_sync ;;
  deploy) cmd_deploy ;;
  prune) cmd_prune ;;
  open-sg) cmd_open_sg ;;
  status) load_state; cmd_status ;;
  worker-logs)
    load_state
    ssh_cmd "docker logs ${WORKER_CONTAINER} --tail ${TAIL_N} -f 2>&1"
    ;;
  *) die "Usage: $0 {sync|deploy|prune|open-sg|status|worker-logs} [--force]" ;;
esac
