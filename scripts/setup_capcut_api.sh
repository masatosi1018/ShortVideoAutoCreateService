#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_DIR="${PROJECT_ROOT}/external/CapCutAPI"

if ! command -v git >/dev/null 2>&1; then
  echo "git が見つかりません。先にインストールしてください。"
  exit 1
fi

mkdir -p "${PROJECT_ROOT}/external"

if ! git -C "${PROJECT_ROOT}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "このプロジェクトはまだ git 管理されていません。"
  echo "先に 'git init' を実行してから再度お試しください。"
  exit 1
fi

if [ ! -d "${TARGET_DIR}" ]; then
  git clone https://github.com/sun-guannan/CapCutAPI.git "${TARGET_DIR}"
else
  echo "external/CapCutAPI は既に存在します。clone はスキップします。"
fi

PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
if [ ! -x "${PYTHON_BIN}" ]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi

if [ -z "${PYTHON_BIN}" ]; then
  echo "Python が見つかりません。先に scripts/bootstrap_env.sh を実行してください。"
  exit 1
fi

"${PYTHON_BIN}" -m venv "${TARGET_DIR}/venv"
source "${TARGET_DIR}/venv/bin/activate"
pip install -r "${TARGET_DIR}/requirements.txt"

cat <<'EOF'
セットアップが完了しました。
サーバー起動は次を実行してください:

  bash scripts/start_capcut_server.sh
EOF
