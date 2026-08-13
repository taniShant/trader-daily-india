#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${CONFIG_PATH:-cicd/env/prod.json}"
ORACLE_USER="${ORACLE_USER:-ubuntu}"
ORACLE_SSH_KEY="${ORACLE_SSH_KEY:-$HOME/.ssh/oracle-key.key}"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Config file not found: ${CONFIG_PATH}" >&2
  exit 2
fi

read_config() {
  python - "$CONFIG_PATH" "$1" <<'PY'
import json
import sys

path, dotted = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as handle:
    value = json.load(handle)
for part in dotted.split("."):
    value = value.get(part, "")
    if value == "":
        break
print(value)
PY
}

read_config_json_b64() {
  python - "$CONFIG_PATH" "$1" <<'PY'
import base64
import json
import sys

path, dotted = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as handle:
    value = json.load(handle)
for part in dotted.split("."):
    value = value.get(part, {})
    if value == {}:
        break
encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
print(base64.b64encode(encoded).decode("ascii"))
PY
}

export ORACLE_USER
export ORACLE_SSH_KEY
export ORACLE_HOST="${ORACLE_HOST:-$(read_config oracle.static_ip)}"
export ORACLE_PROXY_SHARED_SECRET="${ORACLE_PROXY_SHARED_SECRET:-$(read_config oracle.execution_proxy_shared_secret)}"
export ICICI_API_KEY="${ICICI_API_KEY:-$(read_config icici.api_key)}"
export ICICI_SECRET_KEY="${ICICI_SECRET_KEY:-$(read_config icici.secret_key)}"
export ICICI_SESSION_TOKEN="${ICICI_SESSION_TOKEN:-$(read_config icici.session_token)}"
export ORACLE_SYMBOL_MASTER_JSON_B64="${ORACLE_SYMBOL_MASTER_JSON_B64:-$(read_config_json_b64 market_symbols)}"

: "${ORACLE_PROXY_SHARED_SECRET:?Set ORACLE_PROXY_SHARED_SECRET or oracle.execution_proxy_shared_secret before deploying}"

oracle/scripts/deploy_oracle_services.sh "$@"
