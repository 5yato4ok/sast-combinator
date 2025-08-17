#!/bin/sh
set -eu
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
mkdir -p "$OUTPUT_DIR"
echo "[ERROR] CodeQL does not currently support 'rust'. This analyzer is a placeholder."
exit 2
