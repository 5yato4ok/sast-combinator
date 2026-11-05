#!/bin/sh
set -eu

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-eslint_security.sarif}"
CONFIG_PATH="/app/eslint-security.config.mjs"
ESLINT_BIN="/app/node_modules/.bin/eslint"
SARIF_FORMATTER="/app/node_modules/@microsoft/eslint-formatter-sarif/sarif.js"

mkdir -p "$OUTPUT_DIR"
cd "$INPUT_DIR"

# ESLint exits 1 when it reports problems and 2 when it cannot lint.
status=0
"$ESLINT_BIN" . \
  --config "$CONFIG_PATH" \
  --no-error-on-unmatched-pattern \
  --format "$SARIF_FORMATTER" \
  --output-file "$OUTPUT_FILE" || status=$?

if [ "$status" -gt 1 ]; then
  rm -f "$OUTPUT_FILE"
  echo "[ERROR] ESLint failed with exit code $status"
  exit "$status"
fi

echo "[INFO] ESLint (security+TS) SARIF → $OUTPUT_FILE"
