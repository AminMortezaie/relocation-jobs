#!/usr/bin/env bash
# Deploy relocation-jobs panel to EC2 (same host as Postgres + Redis).
#
# Usage:
#   ./scripts/ec2_app_deploy.sh sync        # rsync repo to EC2
#   ./scripts/ec2_app_deploy.sh deploy      # prune + build + run panel + Caddy
#   ./scripts/ec2_app_deploy.sh prune       # free dangling Docker images/build cache
#   ./scripts/ec2_app_deploy.sh open-sg     # open HTTP/HTTPS on security group
#   ./scripts/ec2_app_deploy.sh status      # container + health check
#   ./scripts/ec2_app_deploy.sh worker-logs # tail fetch scheduler logs
#
# Requires: aws-postgres.env, SSH key at ~/Downloads/relocation.pem
# Disk: 8G root fills from leftover panel/worker images; deploy prunes dangling
# images only. BuildKit cache is kept across deploys so tectonic/pip/playwright
# layers are reused — never wiped mid/post-deploy (use `prune` for that).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_FILE="$ROOT/aws-postgres.env"
REMOTE_DIR=/home/ec2-user/relocation-jobs
REGION="${AWS_REGION:-eu-central-1}"
EC2_SSH_USER="${EC2_SSH_USER:-ec2-user}"
EC2_SSH_KEY="${EC2_SSH_KEY:-$HOME/Downloads/relocation.pem}"
PANEL_IMAGE=relocation-panel:ec2
PANEL_CONTAINER=relocation-panel
WORKER_IMAGE=relocation-fetch-worker:ec2
WORKER_CONTAINER=relocation-fetch-worker
CADDY_CONTAINER=relocation-caddy
PANEL_PORT=10000

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

cmd_sync() {
  load_state
  if [[ -d "$ROOT/frontend" ]]; then
    log "Building frontend (board.js)..."
    (cd "$ROOT/frontend" && npm run build --silent)
  fi
  if [[ -d "$ROOT/homepage" ]]; then
    log "Building homepage (static export)..."
    "$ROOT/scripts/build_homepage.sh"
  fi
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
#   docker builder prune -af  # build cache only
# Forbidden in this script (would risk DB wipe):
#   docker volume prune / docker volume rm
#   docker system prune --volumes
#   docker rm -v pg
#   any prune that stops or removes container `pg`
#
# Deploy never wipes BuildKit cache — that is what forces tectonic/pip/playwright
# re-downloads on every deploy. Manual `prune` may reclaim builder cache when
# disk is tight (keeps ~1.5G of recent cache so the next deploy is not cold).
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
  docker builder prune -af --keep-storage 1536MB >/dev/null
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

cmd_deploy() {
  load_state
  local redis_pass db_url redis_url secret admin_pass
  redis_pass="$(redis_password)"
  secret="$(panel_secret)"
  admin_pass="$(admin_password)"
  db_url="postgresql://${DB_USER:-relocation}:${DB_PASSWORD}@172.17.0.1:5432/${DB_NAME:-relocation_jobs}?sslmode=prefer"
  redis_url="redis://:${redis_pass}@172.17.0.1:6379/0"

  cmd_sync
  # Free leftover images from the previous deploy before old+new layers coexist.
  # Skip builder cache — keep pip/tectonic/playwright layers cached between builds.
  remote_docker_prune "" "before builds"

  log "Building ${PANEL_IMAGE} on EC2 (arm64, may take a few minutes)..."
  # --cache-from reuses layers from the live image even if BuildKit cache was trimmed.
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
  ${PANEL_IMAGE}
EOF

  # Drop the previous panel image before the ~2.5GB worker rebuild.
  # Skip builder cache — preserve cached layers for worker build.
  remote_docker_prune "" "after panel"

  log "Building ${WORKER_IMAGE} on EC2 (Playwright, may take several minutes)..."
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
  remote_docker_prune "" "after worker"
  cmd_open_sg
  cmd_status
}

cmd_status() {
  load_state
  local domain="${PANEL_DOMAIN:-kuchup.com}"
  local panel_code domain_code ip_code

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

  log "Panel health (via domain):"
  domain_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "https://${domain}/api/auth/status" 2>/dev/null || echo 000)"
  if [[ "$domain_code" == "200" ]]; then
    log "  https://${domain}/api/auth/status -> ${domain_code} (OK)"
  else
    log "  https://${domain}/api/auth/status -> ${domain_code} (check DNS/TLS if deploy just finished)"
  fi

  log "Origin lock-down (Elastic IP, expect 404):"
  ip_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://${ELASTIC_IP}/api/auth/status" 2>/dev/null || echo 000)"
  log "  http://${ELASTIC_IP}/api/auth/status -> ${ip_code}"
}

cmd_worker_logs() {
  load_state
  local tail_n="${2:-100}"
  ssh_cmd "docker logs ${WORKER_CONTAINER} --tail ${tail_n} -f 2>&1"
}

case "${1:-deploy}" in
  sync) cmd_sync ;;
  deploy) cmd_deploy ;;
  prune) cmd_prune ;;
  open-sg) cmd_open_sg ;;
  status) load_state; cmd_status ;;
  worker-logs) cmd_worker_logs "$@" ;;
  *) die "Usage: $0 {sync|deploy|prune|open-sg|status|worker-logs}" ;;
esac
