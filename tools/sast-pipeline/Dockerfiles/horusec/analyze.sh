#!/usr/bin/env bash
set -euo pipefail
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/horusec_result.sarif"


mkdir -p "$OUTPUT_DIR"
echo "[INFO] Horusec: analyzing $INPUT_DIR"

horusec start -p "$INPUT_DIR" -o sarif -O "${OUTPUT_FILE}" -D=true

echo "[INFO] Results at ${OUTPUT_FILE}"
