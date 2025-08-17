#!/bin/bash
set -e

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-flawfinder_result.sarif}"

echo "[INFO] Running Flawfinder on: $INPUT_DIR"
echo "[INFO] Output will be saved to: $OUTPUT_FILE"

cd "$INPUT_DIR"
flawfinder --sarif . > "$OUTPUT_FILE"

echo "[INFO] Flawfinder analysis complete."