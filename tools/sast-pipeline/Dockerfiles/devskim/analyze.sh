#!/bin/bash
set -e

# Args from docker run
INPUT_DIR="${1:-/workspace/build-tmp/nx_open}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-devskim_result.sarif}"

echo "[INFO] Running DevSkim on: $INPUT_DIR"
echo "[INFO] Output will be saved to: $OUTPUT_FILE"

cd "$INPUT_DIR"
devskim analyze -I . --output-format sarif -O "$OUTPUT_FILE"

echo "[INFO] DevSkim analysis complete."
