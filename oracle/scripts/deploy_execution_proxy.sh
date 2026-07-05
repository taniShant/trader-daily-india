#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Deploy the Oracle execution proxy to an existing Oracle VM.

Usage:
  oracle/scripts/deploy_execution_proxy.sh --dry-run
  oracle/scripts/deploy_execution_proxy.sh

Required environment for real deploy:
  ORACLE_HOST                         Default: 80.225.242.6
  ORACLE_USER                         Default: opc
  ORACLE_SSH_KEY                      Path to SSH private key
  ORACLE_PROXY_SHARED_SECRET          Shared HMAC secret used by AWS client

Optional environment:
  ORACLE_PROXY_PORT                   Default: 8080
  ORACLE_PROXY_MODE                   Default: mock
  REMOTE_APP_DIR                      Default: /opt/trader/oracle-execution-proxy
  ICICI_API_KEY
  ICICI_SECRET_KEY
  ICICI_SESSION_TOKEN
USAGE
}

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
elif [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
elif [[ $# -gt 0 ]]; then
  usage
  exit 2
fi

ORACLE_HOST="${ORACLE_HOST:-80.225.242.6}"
ORACLE_USER="${ORACLE_USER:-opc}"
ORACLE_PROXY_PORT="${ORACLE_PROXY_PORT:-8080}"
ORACLE_PROXY_MODE="${ORACLE_PROXY_MODE:-mock}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-/opt/trader/oracle-execution-proxy}"
LOCAL_APP_DIR="oracle/execution-proxy"
SSH_TARGET="${ORACLE_USER}@${ORACLE_HOST}"
IMAGE_NAME="oracle-execution-proxy:latest"
CONTAINER_NAME="oracle-execution-proxy"

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

echo "Oracle execution proxy deploy"
echo "  host: ${ORACLE_HOST}"
echo "  user: ${ORACLE_USER}"
echo "  mode: ${ORACLE_PROXY_MODE}"
echo "  port: ${ORACLE_PROXY_PORT}"
echo "  remote dir: ${REMOTE_APP_DIR}"
echo "  dry run: ${DRY_RUN}"

SSH_OPTS="-o StrictHostKeyChecking=accept-new"
if [[ "${ORACLE_SSH_KEY:-}" != "" ]]; then
  SSH_OPTS="${SSH_OPTS} -i ${ORACLE_SSH_KEY}"
fi

run "ssh ${SSH_OPTS} ${SSH_TARGET} 'sudo mkdir -p ${REMOTE_APP_DIR} && sudo chown ${ORACLE_USER}:${ORACLE_USER} ${REMOTE_APP_DIR}'"
run "rsync -az -e 'ssh ${SSH_OPTS}' ${LOCAL_APP_DIR}/ ${SSH_TARGET}:${REMOTE_APP_DIR}/"
run "ssh ${SSH_OPTS} ${SSH_TARGET} 'cd ${REMOTE_APP_DIR} && docker build -t ${IMAGE_NAME} .'"

ENV_FILE_CONTENT=$(cat <<EOF
ORACLE_PROXY_MODE=${ORACLE_PROXY_MODE}
ORACLE_STATIC_IP=${ORACLE_HOST}
ORACLE_PROXY_SHARED_SECRET=${ORACLE_PROXY_SHARED_SECRET:-dry-run-secret}
ORACLE_PROXY_MAX_SKEW_SECONDS=${ORACLE_PROXY_MAX_SKEW_SECONDS:-300}
ICICI_API_KEY=${ICICI_API_KEY:-}
ICICI_SECRET_KEY=${ICICI_SECRET_KEY:-}
ICICI_SESSION_TOKEN=${ICICI_SESSION_TOKEN:-}
EOF
)

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[dry-run] write ${REMOTE_APP_DIR}/.env with proxy settings"
else
  printf '%s\n' "$ENV_FILE_CONTENT" | ssh ${SSH_OPTS} "${SSH_TARGET}" "cat > ${REMOTE_APP_DIR}/.env"
fi

run "ssh ${SSH_OPTS} ${SSH_TARGET} 'docker rm -f ${CONTAINER_NAME} >/dev/null 2>&1 || true'"
run "ssh ${SSH_OPTS} ${SSH_TARGET} 'docker run -d --restart unless-stopped --name ${CONTAINER_NAME} --env-file ${REMOTE_APP_DIR}/.env -p ${ORACLE_PROXY_PORT}:8080 ${IMAGE_NAME}'"
run "ssh ${SSH_OPTS} ${SSH_TARGET} 'curl -fsS http://127.0.0.1:${ORACLE_PROXY_PORT}/health'"

echo "Oracle execution proxy deploy script completed."
