#!/bin/sh
set -eu
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-codeql_javascript.sarif}"

LOG_LEVEL="${LOG_LEVEL:-progress}"

LOG_LEVEL="$(echo "$LOG_LEVEL" | tr '[:upper:]' '[:lower:]')"

case "$LOG_LEVEL" in
  info)       LOG_LEVEL="progress" ;;
  debug)      LOG_LEVEL="progress+++" ;;
  errors|warnings|progress|progress+|progress++|progress+++) ;;
  *)          LOG_LEVEL="progress" ;;
esac

mkdir -p "$OUTPUT_DIR"
DB_DIR="/tmp/codeql-db-javascript-typescript"
rm -rf "$DB_DIR" && mkdir -p "$DB_DIR"

echo "[INFO] Creating CodeQL DB for javascript-typescript"
codeql database create "$DB_DIR" --language="javascript-typescript" --source-root "$INPUT_DIR" --verbosity="${LOG_LEVEL}"

QPKG="codeql/typescript-queries:codeql-suites/javascript-security-extended.qls"
echo "[INFO] Analyzing with $QPKG"

codeql database analyze "$DB_DIR" "$QPKG" --format=sarifv2.1.0 --output "$OUTPUT_FILE" --verbosity="${LOG_LEVEL}"

echo "[INFO] Results at $OUTPUT_FILE"
