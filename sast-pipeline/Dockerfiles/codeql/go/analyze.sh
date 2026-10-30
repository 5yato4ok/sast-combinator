#!/bin/sh
set -eu
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-codeql_go.sarif}"
LOG_LEVEL="${LOG_LEVEL:-progress}"

LOG_LEVEL="$(echo "$LOG_LEVEL" | tr '[:upper:]' '[:lower:]')"

case "$LOG_LEVEL" in
  info)       LOG_LEVEL="progress" ;;
  debug)      LOG_LEVEL="progress+++" ;;
  errors|warnings|progress|progress+|progress++|progress+++) ;;
  *)          LOG_LEVEL="progress" ;;
esac

mkdir -p "$OUTPUT_DIR"
DB_DIR="/tmp/codeql-db-go"
rm -rf "$DB_DIR" && mkdir -p "$DB_DIR"

# The analyzer container inherits the builder's volumes, not its filesystem, so a module cache
# under the builder's HOME is unreachable here. The builder writes it to this shared path
# instead (Dockerfiles/builder/builder-entrypoint.sh). GOPROXY=off keeps the build to exactly
# the versions go.sum pinned and needs no credentials or VPN for private modules.
GOMODCACHE_DIR="/workspace/.gomodcache"
if [ -d "$GOMODCACHE_DIR" ]; then
  echo "[INFO] Using Go module cache from $GOMODCACHE_DIR"
  export GOMODCACHE="$GOMODCACHE_DIR"
  export GOFLAGS="-mod=mod"
  export GOPROXY="off"
  export GOPRIVATE="*"
else
  echo "[WARNING] No Go module cache at $GOMODCACHE_DIR; a private dependency will fail to resolve"
fi

echo "[INFO] Creating CodeQL DB for go"
codeql database create "$DB_DIR" --language="go" --source-root "$INPUT_DIR" --verbosity="${LOG_LEVEL}"

QPKG="codeql/go-queries:codeql-suites/go-security-extended.qls"
echo "[INFO] Analyzing with $QPKG"

codeql database analyze "$DB_DIR" "$QPKG" --format=sarifv2.1.0 --output "$OUTPUT_FILE" --verbosity="${LOG_LEVEL}" -j "${JOBS}"

echo "[INFO] Results at $OUTPUT_FILE"
