#!/usr/bin/env bash
# Deploy relocation-jobs panel to EC2 (same host as Postgres + Redis).
#
# Usage:
#   ./scripts/ec2_app_deploy.sh sync     # rsync repo to EC2
#   ./scripts/ec2_app_deploy.sh deploy   # build + run panel + Caddy
#   ./scripts/ec2_app_deploy.sh open-sg  # open HTTP/HTTPS on security group
#   ./scripts/ec2_app_deploy.sh status   # container + health check
#
# Requires: aws-postgres.env, SSH key at ~/Downloads/relocation.pem

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_FILE="$ROOT/aws-postgres.env"
REMOTE_DIR=/home/ec2-user/relocation-jobs
REGION="${AWS_REGION:-eu-central-1}"
EC2_SSH_USER="${EC2_SSH_USER:-ec2-user}"
EC2_SSH_KEY="${EC2_SSH_KEY:-$HOME/Downloads/relocation.pem}"
PANEL_IMAGE=relocation-panel:ec2
PANEL_CONTAINER=relocation-panel
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

cmd_deploy() {
  load_state
  local redis_pass db_url redis_url secret admin_pass
  redis_pass="$(redis_password)"
  secret="$(panel_secret)"
  admin_pass="$(admin_password)"
  db_url="postgresql://${DB_USER:-relocation}:${DB_PASSWORD}@172.17.0.1:5432/${DB_NAME:-relocation_jobs}?sslmode=prefer"
  redis_url="redis://:${redis_pass}@172.17.0.1:6379/0"

  cmd_sync

  log "Building ${PANEL_IMAGE} on EC2 (arm64, may take a few minutes)..."
  ssh_cmd "cd ${REMOTE_DIR} && docker build -f Dockerfile.ec2 -t ${PANEL_IMAGE} ."

  log "Starting panel container..."
  ssh_cmd bash -s <<EOF
set -euo pipefail
docker rm -f ${PANEL_CONTAINER} 2>/dev/null || true
docker run -d --name ${PANEL_CONTAINER} --restart unless-stopped \\
  -p ${PANEL_PORT}:${PANEL_PORT} \\
  -v ${REMOTE_DIR}/relocation_jobs/static:/app/relocation_jobs/static:ro \\
  -e PORT=${PANEL_PORT} \\
  -e PANEL_SCRAPE_ENABLED=0 \\
  -e PANEL_DATA_DIR=/tmp/panel-data \\
  -e PANEL_SECRET_KEY='${secret}' \\
  -e PANEL_ADMIN_USER=admin \\
  -e PANEL_ADMIN_PASSWORD='${admin_pass}' \\
  -e PANEL_ALLOW_REGISTER=0 \\
  -e DATABASE_URL='${db_url}' \\
  -e REDIS_URL='${redis_url}' \\
  ${PANEL_IMAGE}
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

  cmd_open_sg
  cmd_status
}

cmd_status() {
  load_state
  ssh_cmd "docker ps --filter name=relocation- --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
  log "Health (via Elastic IP):"
  curl -sf -o /dev/null -w "  http://${ELASTIC_IP}/api/auth/status -> %{http_code}\n" \
    --max-time 30 "http://${ELASTIC_IP}/api/auth/status" || log "  health check failed (DNS/Caddy still starting?)"
}

case "${1:-deploy}" in
  sync) cmd_sync ;;
  deploy) cmd_deploy ;;
  open-sg) cmd_open_sg ;;
  status) load_state; cmd_status ;;
  *) die "Usage: $0 {sync|deploy|open-sg|status}" ;;
esac
