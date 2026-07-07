#!/usr/bin/env bash
# Ensure Redis on the EC2 Postgres host (Scenario A — same instance as Docker Postgres).
#
# Usage:
#   export REDIS_PASSWORD='...'   # optional; generated if unset
#   ./scripts/ec2_redis.sh ensure # start redis:7-alpine on port 6379
#   ./scripts/ec2_redis.sh url    # print REDIS_URL for .env / Render
#   ./scripts/ec2_redis.sh open-sg # authorize 6379 from your IP (like postgres sync-sg)
#
#   EC2_SSH_KEY=~/Downloads/relocation.pem EC2_SSH_USER=ec2-user  (defaults)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_FILE="$ROOT/aws-postgres.env"
REGION="${AWS_REGION:-eu-central-1}"
CONTAINER_NAME="relocation-redis"
REDIS_PORT=6379
EC2_SSH_USER="${EC2_SSH_USER:-ec2-user}"
EC2_SSH_KEY="${EC2_SSH_KEY:-$HOME/Downloads/relocation.pem}"

ssh_cmd() {
  local key_args=()
  if [[ -f "$EC2_SSH_KEY" ]]; then
    key_args=(-i "$EC2_SSH_KEY")
  fi
  ssh "${key_args[@]}" -o StrictHostKeyChecking=accept-new "${EC2_SSH_USER}@${ELASTIC_IP}" "$@"
}

log() { printf '[redis] %s\n' "$*"; }
die() { printf '[redis] ERROR: %s\n' "$*" >&2; exit 1; }

load_state() {
  [[ -f "$STATE_FILE" ]] || die "Missing $STATE_FILE — run ./scripts/aws_postgres_migrate.sh provision-a first"
  # shellcheck disable=SC1090
  source "$STATE_FILE"
  [[ -n "${ELASTIC_IP:-}" ]] || die "ELASTIC_IP missing in $STATE_FILE"
  [[ -n "${EC2_INSTANCE_ID:-}" ]] || die "EC2_INSTANCE_ID missing in $STATE_FILE"
}

random_password() {
  openssl rand -base64 24 | tr -d '/+=' | head -c 24
}

my_public_ip() {
  curl -sf --max-time 10 https://checkip.amazonaws.com | tr -d '\n'
}

cmd_open_sg() {
  load_state
  require_aws
  IP="$(my_public_ip)"
  [[ -n "$IP" ]] || die "Could not detect public IP"
  SG_ID="$(aws ec2 describe-instances --region "$REGION" --instance-ids "$EC2_INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId' --output text)"
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG_ID" \
    --ip-permissions "IpProtocol=tcp,FromPort=$REDIS_PORT,ToPort=$REDIS_PORT,IpRanges=[{CidrIp=${IP}/32,Description=redis-panel}]" \
    2>/dev/null || log "Port $REDIS_PORT may already be open for $IP"
  log "Security group $SG_ID: TCP $REDIS_PORT from ${IP}/32"
}

require_aws() {
  command -v aws >/dev/null 2>&1 || die "aws CLI not found"
  aws sts get-caller-identity --region "$REGION" >/dev/null 2>&1 \
    || die "AWS credentials missing"
}

cmd_ensure() {
  load_state
  local pass="${REDIS_PASSWORD:-}"
  if [[ -z "$pass" ]]; then
    pass="$(random_password)"
    log "Generated REDIS_PASSWORD (save it): $pass"
  fi
  ssh_cmd bash -s <<EOF
set -euo pipefail
if docker ps -a --format '{{.Names}}' | grep -qx '${CONTAINER_NAME}'; then
  docker start ${CONTAINER_NAME} >/dev/null 2>&1 || true
else
  docker run -d --name ${CONTAINER_NAME} --restart unless-stopped \\
    -p ${REDIS_PORT}:6379 \\
    redis:7-alpine redis-server --requirepass '${pass}'
fi
docker ps --filter name=${CONTAINER_NAME}
EOF
  log "Redis running on ${ELASTIC_IP}:${REDIS_PORT}"
  printf '\nAdd to .env and Render:\nREDIS_URL=redis://:%s@%s:%s/0\n' "$pass" "$ELASTIC_IP" "$REDIS_PORT"
}

cmd_url() {
  load_state
  local pass="${REDIS_PASSWORD:-}"
  [[ -n "$pass" ]] || die "Set REDIS_PASSWORD or run ensure first and save the generated password"
  printf 'redis://:%s@%s:%s/0\n' "$pass" "$ELASTIC_IP" "$REDIS_PORT"
}

case "${1:-}" in
  ensure) cmd_ensure ;;
  url) cmd_url ;;
  open-sg) cmd_open_sg ;;
  *)
    die "Usage: $0 {ensure|url|open-sg}"
    ;;
esac
