#!/bin/sh
set -eu
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-codeql_cpp.sarif}"

mkdir -p "$OUTPUT_DIR"
DB_DIR="/tmp/codeql-db-cpp"
rm -rf "$DB_DIR" && mkdir -p "$DB_DIR"

echo "[INFO] Creating CodeQL DB for cpp"

codeql database create "$DB_DIR" --language="cpp" --source-root "$INPUT_DIR"

QPKG="codeql/cpp-queries"
echo "[INFO] Analyzing with $QPKG"

codeql database analyze "$DB_DIR" "$QPKG" --format=sarifv2.1.0 --output "$OUTPUT_FILE"

echo "[INFO] Results at $OUTPUT_FILE"
