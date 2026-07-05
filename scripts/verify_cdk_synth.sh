#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x ".venv/bin/python" ]]; then
  export PATH="$ROOT_DIR/.venv/bin:$PATH"
elif ! command -v python >/dev/null 2>&1; then
  echo "Missing python. Create .venv locally or install Python in CI first." >&2
  exit 1
fi

mkdir -p .cdk-cache .tmp-home

export CDK_DEPLOY_ENV="${CDK_DEPLOY_ENV:-prod}"
export HOME="$ROOT_DIR/.tmp-home"
export XDG_CACHE_HOME="$ROOT_DIR/.cdk-cache"

cdk synth
