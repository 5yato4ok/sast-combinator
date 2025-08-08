#!/bin/bash
set -e

PROJECT_ROOT="/workspace"

chmod +x project_config.sh

source ./project_config.sh

echo "[+] Warning: Looking for compiler path in $COMPILE_COMMANDS_PATH"

if [ ! -f "$COMPILE_COMMANDS_PATH" ]; then
    echo "[x] File not found: $COMPILE_COMMANDS_PATH"
    exit 1
fi

compiler=$(jq -r '.[0].command' "$COMPILE_COMMANDS_PATH" | awk '{print $1}')

if [ -z "$compiler" ]; then
    echo "[x] Warning: Failed to extract compiler"
fi

export COMPILER_PATH=${compiler}

cd "$PROJECT_ROOT"

echo "[+] Launching analyzers..."

export PYTHONUNBUFFERED=1
python3 /app/run_inside_builder.py
