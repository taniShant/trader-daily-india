#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Deploy Oracle-side services to the existing static-IP Oracle VM.

Usage:
  oracle/scripts/deploy_oracle_services.sh --dry-run
  oracle/scripts/deploy_oracle_services.sh

Required for real deploy:
  ORACLE_SSH_KEY                      Path to SSH private key
  ORACLE_PROXY_SHARED_SECRET          Shared HMAC secret used by AWS client

Optional:
  ORACLE_HOST                         Default: 80.225.242.6
  ORACLE_USER                         Default: opc
  ORACLE_PROXY_MODE                   Default: mock
  ORACLE_COLLECTOR_MODE               Default: live
  ORACLE_PROXY_PORT                   Default: 8080
  ORACLE_COLLECTOR_PORT               Default: 8090
  REMOTE_APP_DIR                      Default: /opt/trader/oracle
  ICICI_API_KEY
  ICICI_SECRET_KEY
  ICICI_SESSION_TOKEN
USAGE
}

DRY_RUN=false
case "${1:-}" in
  --dry-run) DRY_RUN=true ;;
  --help|-h) usage; exit 0 ;;
  "") ;;
  *) usage; exit 2 ;;
esac

ORACLE_HOST="${ORACLE_HOST:-80.225.242.6}"
ORACLE_USER="${ORACLE_USER:-opc}"
ORACLE_PROXY_MODE="${ORACLE_PROXY_MODE:-mock}"
ORACLE_COLLECTOR_MODE="${ORACLE_COLLECTOR_MODE:-live}"
ORACLE_PROXY_PORT="${ORACLE_PROXY_PORT:-8080}"
ORACLE_COLLECTOR_PORT="${ORACLE_COLLECTOR_PORT:-8090}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-/opt/trader/oracle}"
SSH_TARGET="${ORACLE_USER}@${ORACLE_HOST}"
SSH_OPTS="-o StrictHostKeyChecking=accept-new"

if [[ "${ORACLE_SSH_KEY:-}" != "" ]]; then
  SSH_OPTS="${SSH_OPTS} -i ${ORACLE_SSH_KEY}"
fi

run() {
  if [[ "$DRY_RUN" == "true" ]]; then
    printf '[dry-run] %s\n' "$*"
  else
    eval "$@"
  fi
}

require_real_deploy_env() {
  if [[ "$DRY_RUN" == "true" ]]; then
    return
  fi
  : "${ORACLE_SSH_KEY:?Set ORACLE_SSH_KEY to the Oracle VM private key path}"
  : "${ORACLE_PROXY_SHARED_SECRET:?Set ORACLE_PROXY_SHARED_SECRET before deploying}"
}

require_real_deploy_env

echo "Oracle services deploy"
echo "  host: ${ORACLE_HOST}"
echo "  user: ${ORACLE_USER}"
echo "  proxy mode: ${ORACLE_PROXY_MODE}"
echo "  collector mode: ${ORACLE_COLLECTOR_MODE}"
echo "  proxy port: ${ORACLE_PROXY_PORT}"
echo "  collector port: ${ORACLE_COLLECTOR_PORT}"
echo "  remote dir: ${REMOTE_APP_DIR}"
echo "  dry run: ${DRY_RUN}"

run "ssh ${SSH_OPTS} ${SSH_TARGET} 'sudo mkdir -p ${REMOTE_APP_DIR} && sudo chown ${ORACLE_USER}:${ORACLE_USER} ${REMOTE_APP_DIR}'"
run "rsync -az --delete -e 'ssh ${SSH_OPTS}' oracle/ ${SSH_TARGET}:${REMOTE_APP_DIR}/"

ENV_FILE_CONTENT=$(cat <<EOF
ENVIRONMENT=prod
ORACLE_STATIC_IP=${ORACLE_HOST}
ORACLE_PROXY_MODE=${ORACLE_PROXY_MODE}
ORACLE_COLLECTOR_MODE=${ORACLE_COLLECTOR_MODE}
ORACLE_PROXY_PORT=${ORACLE_PROXY_PORT}
ORACLE_COLLECTOR_PORT=${ORACLE_COLLECTOR_PORT}
ORACLE_PROXY_SHARED_SECRET=${ORACLE_PROXY_SHARED_SECRET:-dry-run-secret}
ORACLE_PROXY_MAX_SKEW_SECONDS=${ORACLE_PROXY_MAX_SKEW_SECONDS:-300}
ICICI_API_KEY=${ICICI_API_KEY:-}
ICICI_SECRET_KEY=${ICICI_SECRET_KEY:-}
ICICI_SESSION_TOKEN=${ICICI_SESSION_TOKEN:-}
EOF
)

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[dry-run] write ${REMOTE_APP_DIR}/.env with Oracle service settings"
else
  printf '%s\n' "$ENV_FILE_CONTENT" | ssh ${SSH_OPTS} "${SSH_TARGET}" "cat > ${REMOTE_APP_DIR}/.env && chmod 600 ${REMOTE_APP_DIR}/.env"
fi

run "ssh ${SSH_OPTS} ${SSH_TARGET} 'cd ${REMOTE_APP_DIR} && if command -v docker-compose >/dev/null 2>&1; then docker-compose down --remove-orphans || true; docker-compose up -d --build --remove-orphans; else docker compose down --remove-orphans || true; docker compose up -d --build --remove-orphans; fi'"
run "ssh ${SSH_OPTS} ${SSH_TARGET} 'curl -fsS http://127.0.0.1:${ORACLE_PROXY_PORT}/health'"
run "ssh ${SSH_OPTS} ${SSH_TARGET} 'curl -fsS http://127.0.0.1:${ORACLE_COLLECTOR_PORT}/health'"

echo "Oracle services deploy script completed."
