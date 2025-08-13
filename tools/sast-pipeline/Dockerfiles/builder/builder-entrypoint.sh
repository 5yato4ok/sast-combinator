#!/bin/bash
set -e

PROJECT_ROOT="/workspace"

export RESERVE_CORES="${RESERVE_CORES:-2}"

CORES=$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 1)
export JOBS=$(( CORES > RESERVE_CORES ? CORES - RESERVE_CORES : 1 ))

chmod +x project_config.sh

source ./project_config.sh

if [[ "${NON_COMPILE_PROJECT:-1}" -eq 0 ]]; then

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
fi

cd "$PROJECT_ROOT"

echo "[+] Launching analyzers..."

export PYTHONUNBUFFERED=1
python3 /app/run_inside_builder.py
