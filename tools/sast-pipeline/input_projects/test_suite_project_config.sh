#!/bin/bash
set -e

PROJECT_ROOT="${1:-/workspace}"
PROJECT_BUILD_DIR="${PROJECT_ROOT}/build-tmp"
TEST_SUITE_DIR="${PROJECT_BUILD_DIR}/cooddy-test-suite"
export PROJECT_PATH=${TEST_SUITE_DIR}

cd "$PROJECT_BUILD_DIR"

FORCE_REBUILD=${FORCE_REBUILD:-0}

if [ "$FORCE_REBUILD" == "1" ]; then
  echo "[!] FORCE_REBUILD=1 → removing existing project..."
  rm -rf "$TEST_SUITE_DIR"
fi

if [ -d "$TEST_SUITE_DIR" ]; then
  echo "[=] Project exists. Checking for updates..."

  cd "$TEST_SUITE_DIR"
  git fetch origin

  LOCAL=$(git rev-parse HEAD)
  REMOTE=$(git rev-parse origin/master)

  if [ "$LOCAL" != "$REMOTE" ]; then
    echo "[+] Updates detected. Pulling changes and rebuilding..."
    git pull
  else
    echo "[=] No updates. Skipping build."
  fi

else
  echo "[+] Cloning fresh copy of project..."
  git clone https://github.com/5yato4ok/cooddy-test-suite.git
  ls "${PROJECT_PATH}"
fi

export NON_COMPILE_PROJECT=1