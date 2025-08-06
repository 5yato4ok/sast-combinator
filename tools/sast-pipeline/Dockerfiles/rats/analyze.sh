#!/bin/bash
set -e

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/rats_result.xml"

echo "[+] Running RATS on: $INPUT_DIR"
echo "[+] Output will be saved to: $OUTPUT_FILE"

rats "$INPUT_DIR" --xml > "$OUTPUT_FILE"

echo "[✓] RATS analysis complete."
