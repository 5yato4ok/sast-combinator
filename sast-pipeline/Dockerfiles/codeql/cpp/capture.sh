#!/bin/bash
set -euo pipefail

INPUT_DIR="${1:?Source directory is required}"
ARTIFACT_DIR="${2:?Capture artifact directory is required}"
: "${SAST_BUILD_COMMAND:?Project init must export SAST_BUILD_COMMAND}"
TOOL_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
DB_DIR="$ARTIFACT_DIR/database"

"$TOOL_DIR/codeql" database init "$DB_DIR" --language=cpp --build-mode=manual --source-root "$INPUT_DIR"
"$TOOL_DIR/codeql" database trace-command "$DB_DIR" --working-dir "$INPUT_DIR" -- /bin/bash "$TOOL_DIR/build.sh"
