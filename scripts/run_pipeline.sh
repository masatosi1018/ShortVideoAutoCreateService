#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  echo ".venv の Python が見つかりません。先に 'bash scripts/bootstrap_env.sh' または 'python3 -m venv .venv' を実行してください。" >&2
  exit 1
fi

cd "$ROOT_DIR"
exec "$PYTHON_BIN" src/main.py "$@"
