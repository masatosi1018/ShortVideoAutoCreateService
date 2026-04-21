#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MICROMAMBA_DIR="${PROJECT_ROOT}/.tools"
MICROMAMBA_BIN="${MICROMAMBA_DIR}/micromamba"
MAMBA_ROOT="${PROJECT_ROOT}/.mamba"
ENV_PREFIX="${PROJECT_ROOT}/.venv"

mkdir -p "${MICROMAMBA_DIR}"

if [ ! -x "${MICROMAMBA_BIN}" ]; then
  echo "micromamba をダウンロードしています..."
  curl -L https://micro.mamba.pm/api/micromamba/osx-64/latest | tar -xj -C "${MICROMAMBA_DIR}" --strip-components=1 bin/micromamba
fi

if [ ! -x "${ENV_PREFIX}/bin/python" ]; then
  echo "Python 3.10 + ffmpeg 環境を作成しています..."
  "${MICROMAMBA_BIN}" create -y -r "${MAMBA_ROOT}" -p "${ENV_PREFIX}" python=3.10 ffmpeg pip
fi

echo "依存関係をインストールしています..."
"${ENV_PREFIX}/bin/pip" install -e "${PROJECT_ROOT}"

if [ ! -f "${PROJECT_ROOT}/.env" ]; then
  cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
fi

cat <<'EOF'
セットアップが完了しました。

次のコマンドで確認できます:
  ./.venv/bin/python --version
  ./.venv/bin/ffprobe -version

Phase 1 の実行例:
  ./.venv/bin/python src/main.py --input-file inputs/sample.mp4
EOF

