#!/bin/bash
set -e

PROJECT_ROOT="${1:-/workspace}"
PROJECT_BUILD_DIR="${PROJECT_ROOT}"
NX_DEV_DIR="${PROJECT_BUILD_DIR}/nx"
PROJECT_VERSION="${PROJECT_VERSION:-}"
DEFAULT_BRANCH="${DEFAULT_BRANCH:-master}"
FORCE_REBUILD=${FORCE_REBUILD:-0}

export PROJECT_PATH=${NX_DEV_DIR}
mkdir -p "$PROJECT_BUILD_DIR"


cd "$PROJECT_BUILD_DIR"

if [ "$FORCE_REBUILD" == "1" ]; then
  echo "[WARNING] FORCE_REBUILD=1 → removing existing project..."
  rm -rf "$NX_DEV_DIR"
fi

if [ ! -d "$NX_DEV_DIR/.git" ]; then
  echo "[INFO] Cloning fresh copy of project..."
  git clone "$REPO_URL" "$NX_DEV_DIR"
  REBUILD=1
else
  echo "[INFO] Project exists."
  REBUILD=0
fi

cd "$NX_DEV_DIR"

git fetch --prune --tags origin

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
#if [ "$REBUILD" = "1" ]; then
#
#  echo "[INFO] Installing Python dependencies..."
#  pip3 install -r requirements.txt
#else
#  echo "[INFO] No rebuild needed. Skipping build."
#fi

export PROJECT_PATH=${NX_DEV_DIR}
