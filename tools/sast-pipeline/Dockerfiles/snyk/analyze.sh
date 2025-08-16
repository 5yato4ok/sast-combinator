#!/bin/bash
set -e

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/snyk_result.sarif"

if [[ -z "${SNYK_TOKEN}" ]]; then
    echo "[ERROR] SNYK_TOKEN is not set. Use -e SNYK_TOKEN=... when running container."
    exit 1
fi

echo "[INFO] Running Snyk Code analysis..."
cd "$INPUT_DIR"
if snyk code test --sarif --project-name=. > "$OUTPUT_FILE"; then
    echo "[INFO] Snyk completed with no critical issues."
else
    echo "[ERROR] Snyk found issues or exited with non-zero status (possibly 2)."
fi

echo "[INFO] Snyk analysis complete. Results saved to: $OUTPUT_FILE"
