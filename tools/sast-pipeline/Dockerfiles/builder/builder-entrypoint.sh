#!/bin/bash
set -e

PROJECT_ROOT="/workspace"
PROJECT_BUILD_DIR="${PROJECT_ROOT}/build-tmp"
NX_OPEN_DIR="${PROJECT_BUILD_DIR}/nx_open"

echo "[+] Preparing project directory..."
mkdir -p "$PROJECT_BUILD_DIR"
cd "$PROJECT_BUILD_DIR"

FORCE_REBUILD=${FORCE_REBUILD:-0}

if [ "$FORCE_REBUILD" == "1" ]; then
  echo "[!] FORCE_REBUILD=1 → removing existing project..."
  rm -rf "$NX_OPEN_DIR"
fi

if [ -d "$NX_OPEN_DIR" ]; then
  echo "[=] Project exists. Checking for updates..."

  cd "$NX_OPEN_DIR"
  git fetch origin

  LOCAL=$(git rev-parse HEAD)
  REMOTE=$(git rev-parse origin/master)

  if [ "$LOCAL" != "$REMOTE" ]; then
    echo "[+] Updates detected. Pulling changes and rebuilding..."
    git pull
    REBUILD=1
  else
    echo "[=] No updates. Skipping build."
    REBUILD=0
  fi

else
  echo "[+] Cloning fresh copy of project..."
  git clone https://github.com/networkoptix/nx_open.git
  REBUILD=1
fi

if [ "$REBUILD" == "1" ]; then
  cd "$NX_OPEN_DIR"
  pip3 install -r requirements.txt
  mkdir -p build && cd build
  echo "[+] Configuring and building project..."
  cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DinstallSystemRequirements=ON ..
fi

cd "$PROJECT_ROOT"
echo "[+] Launching analyzers..."

export PYTHONUNBUFFERED=1
python3 /app/run_inside_builder.py
