#!/bin/bash
set -e

PROJECT_ROOT="${1:-/workspace}"
PROJECT_BUILD_DIR="${PROJECT_ROOT}/build-tmp"
JUICY_SHOP_DIR="${PROJECT_BUILD_DIR}/juice-shop"
export PROJECT_PATH=${JUICY_SHOP_DIR}

cd "$PROJECT_BUILD_DIR"

FORCE_REBUILD=${FORCE_REBUILD:-0}

if [ "$FORCE_REBUILD" == "1" ]; then
  echo "[WARNING] FORCE_REBUILD=1 → removing existing project..."
  rm -rf "$JUICY_SHOP_DIR"
fi

if [ -d "$JUICY_SHOP_DIR" ]; then
  echo "[INFO] Project exists. Checking for updates..."

  cd "$JUICY_SHOP_DIR"
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
  echo "[INFO] Installing nodejs..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs

  echo "[INFO] Cloning fresh copy of project..."
  git clone https://github.com/juice-shop/juice-shop.git --depth 1
  cd "${JUICY_SHOP_DIR}"
  echo "[INFO] Installing dependencies..."
  npm install
fi

export NON_COMPILE_PROJECT=0