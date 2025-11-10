#!/usr/bin/env bash
set -euo pipefail

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"

OUTPUT_FILE="${OUTPUT_DIR}/${3:-qodana_python.sarif}"
RESULT_DIR="/results"
SARIF_SRC="${RESULT_DIR}/qodana.sarif.json"

mkdir -p "${RESULT_DIR}"

echo "[INFO] Qodana .NET: analyzing ${INPUT_DIR}"
cd "$INPUT_DIR"
# Токен (если есть) считывается из env: QODANA_TOKEN (не обязателен для community-варианта)
qodana scan \
  --project-dir . \
  --results-dir "${RESULT_DIR}" \
  --config /data/qodana.yaml


if [[ -f "${SARIF_SRC}" ]]; then
  mv "${SARIF_SRC}" "${OUTPUT_FILE}"
  echo "[INFO] Results at ${OUTPUT_FILE}"
else
  echo "[WARN] SARIF not found at ${OUTPUT_FILE}"
fi
