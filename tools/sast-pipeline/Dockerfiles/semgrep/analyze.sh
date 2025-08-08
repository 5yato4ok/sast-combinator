#!/bin/bash
set -e

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/semgrep.sarif"

mkdir -p "$OUTPUT_DIR"

echo "[+] Login to Semgrep..."
semgrep login

echo "[+] Running Semgrep Code analysis..."
cd "$INPUT_DIR"

if semgrep ci --sarif --sarif-output="$OUTPUT_FILE"; then
    echo "[✓] Semgrep completed with no critical issues."
else
    echo "[!] Semgrep found issues or exited with non-zero status."
fi

echo "[✓] Semgrep analysis complete. Results saved to: $OUTPUT_FILE"
