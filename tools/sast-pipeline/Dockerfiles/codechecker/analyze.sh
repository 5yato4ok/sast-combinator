#!/bin/bash
set -e

INPUT_DIR="${1:-/src}"
OUTPUT_DIR="${2:-/shared/output}"
BUILD_DIR="${INPUT_DIR}/build"
COMPILE_COMMANDS="${BUILD_DIR}/compile_commands.json"
REPORT_DIR="${OUTPUT_DIR}/codechecker-reports"

echo "[+] Running CodeChecker on: $INPUT_DIR"
echo "[+] compile_commands.json: $COMPILE_COMMANDS"
echo "[+] Output will be saved to: $REPORT_DIR"

mkdir -p "$REPORT_DIR"

codechecker analyze "$COMPILE_COMMANDS" --output "$REPORT_DIR"
codechecker parse "$REPORT_DIR"

echo "[✓] CodeChecker analysis complete."
