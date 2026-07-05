#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Missing .venv/bin/python. Create and install the project virtualenv first." >&2
  exit 1
fi

mkdir -p .cdk-cache .tmp-home

export CDK_DEPLOY_ENV="${CDK_DEPLOY_ENV:-prod}"
export HOME="$ROOT_DIR/.tmp-home"
export XDG_CACHE_HOME="$ROOT_DIR/.cdk-cache"
export PATH="$ROOT_DIR/.venv/bin:$PATH"

cdk synth
