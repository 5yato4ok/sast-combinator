#!/bin/sh
set -eu

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-njsscan_result.sarif}"

mkdir -p "$OUTPUT_DIR"

# njsscan can output SARIF
njsscan --recursive "$INPUT_DIR" --sarif --output "$OUTPUT_FILE" || {
  echo "[WARN] njsscan returned non-zero exit code (possibly findings found). Continuing…"
}

echo "[INFO] njsscan results at $OUTPUT_FILE"
