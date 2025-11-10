#!/usr/bin/env bash

set -euo pipefail
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-bearer_result.json}"


mkdir -p "$OUTPUT_DIR"
echo "[INFO] Bearer: analyzing $INPUT_DIR"

if bearer scan "$INPUT_DIR" --format json --output "${OUTPUT_FILE}"; then
    echo "[INFO] Bearer completed with no critical issues."
else
    echo "[WARNING] Bearer found issues or exited with non-zero status (possibly 2)."
fi

echo "[INFO] Results at ${OUTPUT_FILE}"
