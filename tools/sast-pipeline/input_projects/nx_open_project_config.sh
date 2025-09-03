#!/bin/bash
set -euo pipefail

PROJECT_ROOT="${1:-/workspace}"
PROJECT_BUILD_DIR="${PROJECT_ROOT}"
NX_OPEN_DIR="${PROJECT_BUILD_DIR}/nx_open"

REPO_URL="${REPO_URL:-https://github.com/networkoptix/nx_open.git}"
DEFAULT_BRANCH="${DEFAULT_BRANCH:-master}"
FORCE_REBUILD="${FORCE_REBUILD:-0}"
PROJECT_VERSION="${PROJECT_VERSION:-}"

echo "[INFO] Preparing project directory..."
mkdir -p "$PROJECT_BUILD_DIR"

if [ "$FORCE_REBUILD" = "1" ]; then
  echo "[INFO] FORCE_REBUILD=1 → removing existing project..."
  rm -rf "$NX_OPEN_DIR"
fi

if [ ! -d "$NX_OPEN_DIR/.git" ]; then
  echo "[INFO] Cloning fresh copy of project..."
  git clone "$REPO_URL" "$NX_OPEN_DIR"
  REBUILD=1
else
  echo "[INFO] Project exists."
  REBUILD=0
fi

cd "$NX_OPEN_DIR"

# Always update links to origin to find required version
git fetch --prune --tags origin

# Search for target revision
if [ -n "$PROJECT_VERSION" ]; then
  # PROJECT_VERSION can be commit, tag, branch
  if git rev-parse -q --verify "${PROJECT_VERSION}^{commit}" >/dev/null; then
    TARGET_COMMIT=$(git rev-parse "${PROJECT_VERSION}^{commit}")
  elif git rev-parse -q --verify "origin/${PROJECT_VERSION}^{commit}" >/dev/null; then
    TARGET_COMMIT=$(git rev-parse "origin/${PROJECT_VERSION}^{commit}")
  else
    echo "[ERROR] Can't resolve PROJECT_VERSION='$PROJECT_VERSION' (no commit/tag/branch found)." >&2
    exit 1
  fi
  TARGET_DESC="$PROJECT_VERSION"
else
  TARGET_COMMIT=$(git rev-parse "origin/${DEFAULT_BRANCH}")
  TARGET_DESC="origin/${DEFAULT_BRANCH}"
fi

CURRENT_COMMIT=$(git rev-parse HEAD)

if [ "$CURRENT_COMMIT" != "$TARGET_COMMIT" ]; then
  echo "[INFO] Switching to desired ref: $TARGET_DESC"
  # For default branch leave it, for some version - detached HEAD
  if [ -z "$PROJECT_VERSION" ]; then
    git switch -C "$DEFAULT_BRANCH" "origin/${DEFAULT_BRANCH}"
  else
    git -c advice.detachedHead=false checkout --detach "$TARGET_COMMIT"
  fi
  REBUILD=1
else
  echo "[INFO] Already on desired ref ($TARGET_DESC @ $CURRENT_COMMIT)."
fi

if [ "$REBUILD" = "1" ]; then

  echo "[INFO] Installing Python dependencies..."
  pip3 install -r requirements.txt

  echo "[INFO] Configuring and building project..."

  cmake -S "$NX_OPEN_DIR" -B "$NX_OPEN_DIR/build" \
        -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
        -DinstallSystemRequirements=ON

  cmake --build "$NX_OPEN_DIR/build" --clean-first --parallel "$JOBS"
else
  echo "[INFO] No rebuild needed. Skipping build."
fi

export PROJECT_PATH="${NX_OPEN_DIR}"
export COMPILE_COMMANDS_PATH="${NX_OPEN_DIR}/build/compile_commands.json"
export NON_COMPILE_PROJECT=0