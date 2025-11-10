#!/bin/bash
set -e

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
REPORT_DIR="${OUTPUT_DIR}/codechecker-reports"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-infer_result.json}"

# Determine quiet options for apt-get based on LOG_LEVEL
LOG_LEVEL="${LOG_LEVEL:-INFO}"

echo "[INFO] Checking..."

if [ -f "$COMPILE_COMMANDS_PATH" ]; then
    echo "[INFO] Compile commands exist: $COMPILE_COMMANDS_PATH"
else
    echo "[WARNING] Compile commands not exist: $COMPILE_COMMANDS_PATH"
    exit 2
fi

if [[ ! -x "$COMPILER_PATH" ]]; then
    echo "[WARNING] Compiler not found or not executable: $COMPILER_PATH"
    exit 2
fi

echo "[INFO] Setting up environment."

COMPILER_DIR="$(dirname "$COMPILER_PATH")"

# Add compiler directory to PATH if not already included
if [[ ":$PATH:" != *":$COMPILER_DIR:"* ]]; then
    export PATH="$COMPILER_DIR:$PATH"
    echo "[INFO] Added to PATH: $COMPILER_DIR"
else
    echo "[INFO] Compiler directory already in PATH: $COMPILER_DIR"
fi


echo "[INFO] Running infer on: $COMPILE_COMMANDS_PATH"
echo "[INFO] Output will be saved to: $REPORT_DIR"

mkdir -p "$REPORT_DIR"
JSON_RAW="/tmp/infer_report.json"

if infer run --compilation-database "$COMPILE_COMMANDS_PATH"; then
    echo "[INFO] Infer analyze completed with no critical issues."
else
    echo "[ERROR] Infer found issues or exited with non-zero status (possibly 3)."
fi

echo "[INFO] Infer analysis complete."

echo "[INFO] Generating JSON report: $JSON_PATH"

if infer report > "$JSON_RAW"; then
    echo "[INFO] Infer report completed with no critical issues."
else
    echo "[ERROR] Infer report found issues or exited with non-zero status (possibly 2)."
fi

echo "[INFO] Converting report"
python3 convert_report.py "$JSON_RAW" "$OUTPUT_FILE"
cp "$JSON_RAW" "$OUTPUT_DIR"


