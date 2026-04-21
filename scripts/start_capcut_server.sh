#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CAPCUT_DIR="${PROJECT_ROOT}/external/CapCutAPI"
VENV_DIR="${CAPCUT_DIR}/venv"

if [ ! -d "${CAPCUT_DIR}" ]; then
  echo "external/CapCutAPI が見つかりません。先に scripts/setup_capcut_api.sh を実行してください。"
  exit 1
fi

if [ ! -d "${VENV_DIR}" ]; then
  echo "CapCutAPI の仮想環境が見つかりません。先に scripts/setup_capcut_api.sh を実行してください。"
  exit 1
fi

source "${VENV_DIR}/bin/activate"
cd "${CAPCUT_DIR}"
python capcut_server.py

