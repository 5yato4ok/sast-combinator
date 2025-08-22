#!/bin/bash
set -e

PROJECT_ROOT="${1:-/workspace}"
PROJECT_BUILD_DIR="${PROJECT_ROOT}/build-tmp"
REPO_DIR="${PROJECT_BUILD_DIR}/VulnerableCoreApp"
ICU_DIR="${REPO_DIR}/icu_libs"
export PROJECT_PATH=${REPO_DIR}
export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1

cd "$PROJECT_BUILD_DIR"

FORCE_REBUILD=${FORCE_REBUILD:-0}

if [ "$FORCE_REBUILD" == "1" ]; then
  echo "[WARNING] FORCE_REBUILD=1 → removing existing project..."
  rm -rf "$REPO_DIR"
fi

if [ -d "$REPO_DIR" ]; then
  echo "[INFO] Project exists. Checking for updates..."

  cd "$REPO_DIR"
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
  git clone https://github.com/zsusac/VulnerableCoreApp.git --depth 1
  cd "${REPO_DIR}"

  echo "[INFO] Installing dependencies"

  mkdir -p ./libssl
  wget http://security.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2.24_amd64.deb -O /tmp/libssl1.1.deb
  dpkg -x /tmp/libssl1.1.deb ./libssl
  rm /tmp/libssl1.1.deb

  apt update
  mkdir -p /tmp/download && cd /tmp/download

  apt-get download libicu70 || apt-get download libicu66 || apt-get download libicu72 || apt-get download libicu74
  mkdir -p "$ICU_DIR"
  dpkg-deb -x libicu*.deb "$ICU_DIR"
  rm -f libicu*.deb

  LIBDIR="$(find "$ICU_DIR" -type d -name x86_64-linux-gnu -o -name lib64 | head -n1)"
  cd "$LIBDIR"
  for base in icui18n icuuc icudata; do
    sofile="$(ls lib${base}.so.* 2>/dev/null | head -n1)"
    [ -n "$sofile" ] && ln -sf "$sofile" "lib${base}.so"
  done

  echo "[INFO] Installing dotnet to local folder..."
  # Add Microsoft package repository
  mkdir -p .dotnet
  curl -sSL https://dot.net/v1/dotnet-install.sh -o dotnet-install.sh
  chmod +x dotnet-install.sh

  source ./dotnet-install.sh --version 2.1.816 --install-dir "$REPO_DIR/.dotnet"

  echo "[INFO] Installing dependencies..."

  export PATH="${REPO_DIR}/.dotnet:$PATH"
  export LD_LIBRARY_PATH="${LIBDIR}:${REPO_DIR}/libssl/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-""}"
  cd "${REPO_DIR}"
  dotnet build
fi

export NON_COMPILE_PROJECT=0
export DOTNET_PATH="${REPO_DIR}/.dotnet"
export LIB_PATH="${REPO_DIR}/libssl/usr/lib/x86_64-linux-gnu"