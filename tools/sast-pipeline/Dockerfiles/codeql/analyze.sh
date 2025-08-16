#!/usr/bin/env bash

set -euo pipefail

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/codeql_result.sarif"

mkdir -p "$OUTPUT_DIR"

if [[ -z "${CODEQL_LANGUAGE}" ]]; then
  echo "[ERROR] Set CODEQL_LANGUAGE (python/cpp/csharp/javascript/typescript)"
  exit 2
fi

DB_DIR="/tmp/codeql-db"
rm -rf "$DB_DIR" && mkdir -p "$DB_DIR"

echo "[INFO] Creating CodeQL DB for ${CODEQL_LANGUAGE}"

cd "$INPUT_DIR"
codeql database create "$DB_DIR" --language="${CODEQL_LANGUAGE}" .


case "${CODEQL_LANGUAGE}" in
  python) QPKG="codeql/python-queries";;
  cpp|c) QPKG="codeql/cpp-queries";;
  csharp) QPKG="codeql/csharp-queries";;
  javascript|typescript) QPKG="codeql/javascript-queries";;
  *) QPKG="codeql/${CODEQL_LANGUAGE}-queries";;
esac

codeql database analyze "$DB_DIR" "$QPKG" --format=sarifv2.1.0 --output "${OUTPUT_FILE}"

echo "[INFO] Results at ${OUTPUT_FILE}"
