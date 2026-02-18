#!/bin/bash
set -e

PROJECT_ROOT="${1:-/workspace}"
PROJECT_BUILD_DIR="${PROJECT_ROOT}"
DEV_DIR="${PROJECT_BUILD_DIR}/${PROJECT_NAME}"
PROJECT_VERSION="${PROJECT_VERSION:-}"
DEFAULT_BRANCH="${DEFAULT_BRANCH:-master}"
FORCE_REBUILD=${FORCE_REBUILD:-0}

export PROJECT_PATH=${DEV_DIR}
mkdir -p "$PROJECT_BUILD_DIR"

install_with_log() {
  local name="$1"
  shift

  echo "[NODE] Try: $name"
  "$@"
  local rc=$?

  if [ "$rc" -ne 0 ]; then
    echo "[NODE][WARN] $name failed with code=$rc"
  else
    echo "[NODE] $name succeeded"
  fi

  return "$rc"
}

install_node_deps() {
  local dir="$1"

  echo "[NODE] Installing dependencies in: $dir"
  cd "$dir"
  set +e

  if [ -f "pnpm-lock.yaml" ]; then
    install_with_log "corepack enable" corepack enable
    install_with_log "corepack prepare pnpm --activate" corepack prepare pnpm --activate
    install_with_log "pnpm install --frozen-lockfile" pnpm install --frozen-lockfile && {
      set -e
      return 0
    }
    install_with_log "pnpm install" pnpm install && {
      set -e
      return 0
    }
    install_with_log "npm install (fallback)" npm install && {
      set -e
      return 0
    }
  elif [ -f "yarn.lock" ]; then
    install_with_log "corepack enable" corepack enable
    install_with_log "corepack prepare yarn --activate" corepack prepare yarn --activate
    install_with_log "yarn install --frozen-lockfile" yarn install --frozen-lockfile && {
      set -e
      return 0
    }
    install_with_log "yarn install" yarn install && {
      set -e
      return 0
    }
    install_with_log "npm install (fallback)" npm install && {
      set -e
      return 0
    }
  elif [ -f "package-lock.json" ] && [ -f "package.json" ]; then
    install_with_log "npm ci" npm ci && {
      set -e
      return 0
    }
    install_with_log "npm install (fallback)" npm install && {
      set -e
      return 0
    }
  elif [ -f "package-lock.json" ]; then
    set -e
    echo "[NODE][WARN] package-lock.json found without package.json in: $dir. Skipping."
    return 0
  elif [ -f "package.json" ]; then
    install_with_log "npm install" npm install && {
      set -e
      return 0
    }
  fi

  set -e
  echo "[NODE][ERROR] All dependency installation methods failed"
  return 1
}


cd "$PROJECT_BUILD_DIR"

if [ "$FORCE_REBUILD" == "1" ]; then
  echo "[WARNING] FORCE_REBUILD=1 → removing existing project..."
  rm -rf "$DEV_DIR"
fi

if [ ! -d "$DEV_DIR/.git" ]; then
  echo "[INFO] Cloning fresh copy of project..."
  git clone "$REPO_URL" "$DEV_DIR"
  REBUILD=1
else
  echo "[INFO] Project exists."
  REBUILD=0
fi

cd "$DEV_DIR"

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

if [ -f "requirements.txt" ]; then
  echo "Installing python dependencies"
  pip3 install -r requirements.txt
fi

NEED_NODE=0
if [ -f "package.json" ] || [ -f "yarn.lock" ] || [ -f "pnpm-lock.yaml" ] || [ -f "package-lock.json" ]; then
  NEED_NODE=1
fi

if [ "$NEED_NODE" -eq 1 ]; then
  echo "[NODE] Installing Node.js"
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

if [ "$NEED_NODE" -eq 1 ]; then
  set +e
  install_node_deps "$DEV_DIR"
  node_install_rc=$?
  set -e

  if [ "$node_install_rc" -ne 0 ]; then
    echo "[NODE][ERROR] Dependencies installation failed for all valid Node projects; continuing without Node deps"
  fi
fi

if [ -f "pyproject.toml" ]; then
  echo "Installing poetry project dependencies"
  pip3 install poetry
  poetry install
fi

if [ -f "requirements-system.txt" ]; then
  echo "Installing system dependencies"
  xargs -a requirements-system.txt apt-get install -y
fi

export PROJECT_PATH=${DEV_DIR}
