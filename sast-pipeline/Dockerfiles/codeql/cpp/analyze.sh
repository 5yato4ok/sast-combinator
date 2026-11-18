#!/bin/bash
set -euo pipefail
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-codeql_cpp.sarif}"
LOG_LEVEL="${LOG_LEVEL:-progress}"
ARTIFACT_DIR="${4:?A captured build from the prepared builder is required}"

LOG_LEVEL="$(echo "$LOG_LEVEL" | tr '[:upper:]' '[:lower:]')"

case "$LOG_LEVEL" in
  info)       LOG_LEVEL="progress" ;;
  debug)      LOG_LEVEL="progress+++" ;;
  errors|warnings|progress|progress+|progress++|progress+++) ;;
  *)          LOG_LEVEL="progress" ;;
esac

mkdir -p "$OUTPUT_DIR"
DB_DIR="$ARTIFACT_DIR/database"
RESOURCE_ARGS=("--threads=${JOBS:-0}")
if [[ -n "${CODEQL_RAM_MB:-}" ]]; then
  RESOURCE_ARGS+=("--ram=$CODEQL_RAM_MB")
fi

echo "[INFO] Finalizing captured C/C++ database"
codeql database finalize "$DB_DIR" "${RESOURCE_ARGS[@]}" --verbosity="${LOG_LEVEL}"

QPKG="codeql/cpp-queries@${CODEQL_QUERIES_VERSION:?Query pack version must be pinned by the image}:codeql-suites/cpp-security-extended.qls"
echo "[INFO] Analyzing with $QPKG"

codeql database analyze "$DB_DIR" "$QPKG" --format=sarifv2.1.0 --output "$OUTPUT_FILE" --verbosity="${LOG_LEVEL}" "${RESOURCE_ARGS[@]}"

echo "[INFO] Results at $OUTPUT_FILE"
