#!/bin/sh
set -eu
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-codeql_typescript.sarif}"

mkdir -p "$OUTPUT_DIR"
DB_DIR="/tmp/codeql-db-typescript"
rm -rf "$DB_DIR" && mkdir -p "$DB_DIR"

echo "[INFO] Creating CodeQL DB for typescript"
codeql database create "$DB_DIR" --language="typescript" --source-root "$INPUT_DIR"

QPKG="codeql/javascript-queries"
echo "[INFO] Analyzing with $QPKG"

codeql database analyze "$DB_DIR" "$QPKG" --format=sarifv2.1.0 --output "$OUTPUT_FILE"

echo "[INFO] Results at $OUTPUT_FILE"
