#!/bin/sh
set -eu

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-eslint_security.sarif}"
CONFIG_PATH="/app/eslint-security.config.mjs"

mkdir -p "$OUTPUT_DIR"

# Используем глобальный ESLint из образа, а не npx (который может взять локальный из проекта)
ESLINT_BIN="$(command -v eslint || true)"
if [ -z "$ESLINT_BIN" ]; then
  echo "[ERROR] Global eslint not found in PATH"; exit 2
fi

cd "$INPUT_DIR"

# ESLint v9 + flat-config + SARIF
if ! "$ESLINT_BIN" . \
  --no-eslintrc \
  --config "$CONFIG_PATH" \
  --no-error-on-unmatched-pattern \
  --format @microsoft/eslint-formatter-sarif \
  > "$OUTPUT_FILE"; then
  echo "[WARN] ESLint exited non-zero"
fi

echo "[INFO] ESLint (security+TS) SARIF → $OUTPUT_FILE"
