#!/bin/bash
set -e

PROJECT_ROOT="${1:-/workspace}"
PROJECT_BUILD_DIR="${PROJECT_ROOT}"
COB_DIR="${PROJECT_BUILD_DIR}"

export PROJECT_PATH=${COB_DIR}

cd "$PROJECT_BUILD_DIR"

FORCE_REBUILD=${FORCE_REBUILD:-0}

if [ "$FORCE_REBUILD" == "1" ]; then
  echo "[WARNING] FORCE_REBUILD=1 → removing existing project..."
  rm -rf "$COB_DIR"
fi


if [ -d "$COB_DIR" ]; then
  echo "[INFO] Project exists. Install dependencies..."
  cd "${COB_DIR}"
  pip3 install --user -r requirements.txt
else
  echo "[ERROR] Project directory desn't exist"
  exit 1
fi
