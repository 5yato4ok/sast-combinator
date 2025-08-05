#!/bin/bash
set -e

INPUT_DIR="${1:-/src}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/cppcheck_result.sarif"

echo "[+] Running Cppcheck on: $INPUT_DIR"
echo "[+] Output will be saved to: $OUTPUT_FILE"

cppcheck \
    --output-format=sarif \
    --output-file="$OUTPUT_FILE" \
    --check-level=exhaustive \
    -j "$(nproc)" \
    "$INPUT_DIR"

echo "[✓] Cppcheck analysis complete."
