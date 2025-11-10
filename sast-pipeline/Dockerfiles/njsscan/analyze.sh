#!/bin/sh
set -eu

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-njsscan_result.sarif}"

mkdir -p "$OUTPUT_DIR"

echo "[INFO] Launch njsscan"
cd "$INPUT_DIR"
njsscan . --sarif -o "$OUTPUT_FILE" || {
  echo "[WARN] njsscan returned non-zero"
}

echo "[INFO] njsscan SARIF report → $OUTPUT_FILE"
