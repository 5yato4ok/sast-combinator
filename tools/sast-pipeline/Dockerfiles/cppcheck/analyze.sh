#!/bin/bash
set -e

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/cppcheck_result.sarif"

echo "[INFO] Running Cppcheck on: $INPUT_DIR"
echo "[INFO] Output will be saved to: $OUTPUT_FILE"

cd "$INPUT_DIR"
cppcheck \
    --output-format=sarif \
    --output-file="$OUTPUT_FILE" \
    --check-level=exhaustive \
    -j "$(nproc)" \
    .

echo "[INFO] Cppcheck analysis complete."
