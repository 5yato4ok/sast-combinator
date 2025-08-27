#!/bin/bash
set -e

PROJECT_ROOT="${1:-/workspace}"
PROJECT_BUILD_DIR="${PROJECT_ROOT}/build-tmp"
REPO_PATH="${PROJECT_BUILD_DIR}/DVWA"
export PROJECT_PATH=${REPO_PATH}

cd "$PROJECT_BUILD_DIR"

FORCE_REBUILD=${FORCE_REBUILD:-0}

if [ "$FORCE_REBUILD" == "1" ]; then
  echo "[WARNING] FORCE_REBUILD=1 → removing existing project..."
  rm -rf "$REPO_PATH"
fi

if [ -d "$REPO_PATH" ]; then
  echo "[INFO] Project exists. Checking for updates..."

  cd "$REPO_PATH"
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
  git clone https://github.com/digininja/DVWA.git --depth 1
fi
