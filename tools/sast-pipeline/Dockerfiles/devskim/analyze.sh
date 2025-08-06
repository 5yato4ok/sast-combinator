#!/bin/bash
set -e

# Args from docker run
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/devskim_result.sarif"

echo "[+] Running DevSkim on: $INPUT_DIR"
echo "[+] Output will be saved to: $OUTPUT_FILE"

ls $INPUT_DIR

devskim analyze -I "$INPUT_DIR" --output-format sarif -O "$OUTPUT_FILE"

echo "[✓] DevSkim analysis complete."
