#!/bin/sh
set -eu

# Positional args: INPUT_DIR OUTPUT_DIR OUTPUT_FILE
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${3:-resharper.sarif.json}"

INSPECT="/opt/resharper/inspectcode.sh"

mkdir -p "$OUTPUT_DIR"

# Map LOG_LEVEL (if present) to InspectCode verbosity
# Accepted by InspectCode: OFF | ERROR | WARN | INFO | VERBOSE | TRACE
VERBOSITY="WARN"
if [ "${LOG_LEVEL:-}" ]; then
  lower="$(printf '%s' "$LOG_LEVEL" | tr '[:upper:]' '[:lower:]')"
  case "$lower" in
    errors)    VERBOSITY="ERROR" ;;
    warnings)  VERBOSITY="WARN" ;;
    info)      VERBOSITY="WARN" ;;
    debug)     VERBOSITY="INFO" ;;
    progress|progress* ) VERBOSITY="INFO" ;;
    *)         VERBOSITY="WARN" ;;
  esac
fi

# Environment for .NET runtime
export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
export PATH="${DOTNET_PATH}:${PATH-}"

if [ -n "${LIB_PATH:-}" ]; then
  export LD_LIBRARY_PATH="${LIB_PATH}:${LD_LIBRARY_PATH-}"
fi

# Locate a .sln within INPUT_DIR (up to 3 levels deep)
cd "$INPUT_DIR"
TARGET="$(find . -maxdepth 3 -type f \( -name '*.sln' -o -name '*.csproj' -o -name '*.vbproj' \) | head -n 1 || true)"
if [ -z "$TARGET" ]; then
  echo "[ERROR] .sln file not found under $INPUT_DIR"
  exit 2
fi

echo "[INFO] Running ReSharper InspectCode"
echo "[INFO] Project file: $TARGET"
echo "[INFO] Verbosity: $VERBOSITY"
echo "[INFO] Output: $OUTPUT_DIR/$OUTPUT_FILE"

# Run InspectCode with SARIF output, no profiles
"$INSPECT" "$TARGET" \
  --format=Sarif \
  --output="$OUTPUT_DIR/$OUTPUT_FILE" \
  --verbosity="$VERBOSITY"

if [ -f "$OUTPUT_DIR/$OUTPUT_FILE" ]; then
  echo "[INFO] SARIF saved to $OUTPUT_DIR/$OUTPUT_FILE"
else
  echo "[WARN] SARIF was not created"
fi
