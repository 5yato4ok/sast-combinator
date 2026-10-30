#!/bin/bash
set -e

PROJECT_ROOT="/workspace"

export RESERVE_CORES="${RESERVE_CORES:-2}"

CORES=$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 1)
export JOBS=$(( CORES > RESERVE_CORES ? CORES - RESERVE_CORES : 1 ))

# Go module cache on the shared volume, not under this container's HOME: an analyzer container
# inherits this builder's volumes but not its filesystem, so anything a project script downloads
# outside PROJECT_ROOT is invisible to the analyzer that has to rebuild the project. PROJECT_ROOT
# is the mount, while analyzers scan $PROJECT_PATH below it, so the cache stays out of their input.
export GOMODCACHE="${PROJECT_ROOT}/.gomodcache"

chmod +x project_config.sh

source ./project_config.sh

if [[ "${NON_COMPILE_PROJECT:-1}" -eq 0 && -n "${COMPILE_COMMANDS_PATH:-}" ]]; then

  echo "[INFO] Looking for compiler path in $COMPILE_COMMANDS_PATH"

  if [ ! -f "$COMPILE_COMMANDS_PATH" ]; then
      echo "[WARNING] File not found: $COMPILE_COMMANDS_PATH"
      exit 1
  fi

  compiler=$(jq -r '.[0].command' "$COMPILE_COMMANDS_PATH" | awk '{print $1}')

  if [ -z "$compiler" ]; then
      echo "[WARNING] Failed to extract compiler"
      exit 1
  fi

  export COMPILER_PATH=${compiler}
fi

cd "$PROJECT_ROOT"

echo "[INFO] Launching analyzers..."

export PYTHONUNBUFFERED=1
/usr/bin/python3 /app/run_inside_builder.py
