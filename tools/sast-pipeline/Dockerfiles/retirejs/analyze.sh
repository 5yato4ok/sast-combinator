#!/bin/bash
set -eu


INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-retirejs.json}"


LOG_LEVEL="${LOG_LEVEL:-INFO}"

RETIRE_VERBOSE=""

if [[ "${LOG_LEVEL}" != "DEBUG" ]]; then
    RETIRE_VERBOSE=""
else
    RETIRE_VERBOSE="--verbose"
fi

mkdir -p "$OUTPUT_DIR"

retire --path "$INPUT_DIR" --outputformat json $RETIRE_VERBOSE > "$OUTPUT_FILE" || {
  echo "[WARN] retire.js returned non-zero (likely findings). Continuing..."
}

echo "[INFO] Retire.js JSON report → $OUTPUT_FILE"