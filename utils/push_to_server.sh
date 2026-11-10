#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_ENV_FILE="${COMPOSE_ENV_FILE:-.env}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

REMOTE_DESTINATION=$(python3 "$PROJECT_DIR/scripts/deployment_config.py" \
  --project-dir "$PROJECT_DIR" --env-file "$COMPOSE_ENV_FILE" \
  --compose-file "$COMPOSE_FILE" --sync-destination)

# Keep the destination's configuration and persistent uploads when synchronizing code.
rsync -avz --delete --exclude '__pycache__' --exclude 'media/' \
  --exclude '.env*' --exclude '.sdlc/work/' \
  "$PROJECT_DIR/" "$REMOTE_DESTINATION"
