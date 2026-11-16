#!/bin/sh
set -eu

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-horusec_result.json}"

mkdir -p "$OUTPUT_DIR"

# Horusec opens every scanned file at once and does not raise its own limit; the container's
# default soft limit of 1024 aborts the scan with "too many open files".
# shellcheck disable=SC3045 # the image's busybox sh implements ulimit -n and -H
ulimit -n "$(ulimit -Hn)"

echo "[INFO] Horusec: analyzing $INPUT_DIR"
cd "${INPUT_DIR}"
horusec start -p . -o json -O "$OUTPUT_FILE" -D=true

# Horusec exits 0 even when its engine fails; the report's own status says whether the scan ran.
if ! jq -e '.status == "success"' "$OUTPUT_FILE" >/dev/null; then
  echo "[ERROR] Horusec scan failed: $(jq -r '.errors // "no error detail"' "$OUTPUT_FILE")"
  rm -f "$OUTPUT_FILE"
  exit 1
fi

# A clean scan reports null where the importer expects a list.
NORMALIZED="${OUTPUT_FILE}.tmp"
jq '.analysisVulnerabilities //= [] | .errors //= ""' "$OUTPUT_FILE" > "$NORMALIZED"
mv "$NORMALIZED" "$OUTPUT_FILE"

echo "[INFO] Results at $OUTPUT_FILE"
