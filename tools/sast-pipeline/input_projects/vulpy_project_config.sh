#!/bin/bash
set -e

PROJECT_ROOT="${1:-/workspace}"
PROJECT_BUILD_DIR="${PROJECT_ROOT}/build-tmp"
VULPY_DIR="${PROJECT_BUILD_DIR}/vulpy"

export PROJECT_PATH=${VULPY_DIR}

cd "$PROJECT_BUILD_DIR"

FORCE_REBUILD=${FORCE_REBUILD:-0}

if [ "$FORCE_REBUILD" == "1" ]; then
  echo "[WARNING] FORCE_REBUILD=1 → removing existing project..."
  rm -rf "$VULPY_DIR"
fi


if [ -d "$VULPY_DIR" ]; then
  echo "[INFO] Project exists. Checking for updates..."

  cd "$VULPY_DIR"
  git fetch origin

  LOCAL=$(git rev-parse HEAD)
  REMOTE=$(git rev-parse origin/master)

  if [ "$LOCAL" != "$REMOTE" ]; then
    echo "[INFO] Updates detected. Pulling changes and rebuilding..."
    git pull
  else
    echo "[INFO] No updates. Skipping build."
  fi

else
  echo "[INFO] Cloning fresh copy of project..."
  git clone https://github.com/fportantier/vulpy
  cd "${VULPY_DIR}"
  pip3 install --user -r requirements.txt
fi





