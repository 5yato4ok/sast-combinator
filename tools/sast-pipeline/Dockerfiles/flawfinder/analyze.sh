#!/bin/bash
set -e

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/flawfinder_results.sarif"

echo "[+] Running Flawfinder on: $INPUT_DIR"
echo "[+] Output will be saved to: $OUTPUT_FILE"

flawfinder --sarif "$INPUT_DIR" > "$OUTPUT_FILE"

echo "[✓] Flawfinder analysis complete."