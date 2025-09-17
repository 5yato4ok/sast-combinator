#!/usr/bin/env bash
set -euo pipefail

# Positional args: INPUT_DIR OUTPUT_DIR OUTPUT_FILE
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${3:-resharper.sarif.json}"

INSPECT="/opt/resharper/inspectcode.sh"

# Map LOG_LEVEL (if present) to InspectCode verbosity
# Accepted by InspectCode: OFF | ERROR | WARN | INFO | VERBOSE | TRACE
to_lower() { tr '[:upper:]' '[:lower:]'; }
VERBOSITY="INFO"
if [[ "${LOG_LEVEL:-}" != "" ]]; then
  case "$(echo "$LOG_LEVEL" | to_lower)" in
    errors)    VERBOSITY="ERROR" ;;
    warnings)  VERBOSITY="WARN" ;;
    info)      VERBOSITY="INFO" ;;
    debug)     VERBOSITY="TRACE" ;;
    progress|progress+|progress++|progress+++) VERBOSITY="INFO" ;;
    *)         VERBOSITY="INFO" ;;
  esac
fi


export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
export PATH="$DOTNET_PATH:$PATH"
export LD_LIBRARY_PATH="${LIB_PATH}:${LD_LIBRARY_PATH-}"

mkdir -p "$OUTPUT_DIR"

# Locate a .sln within INPUT_DIR (up to 3 levels deep)
cd "$INPUT_DIR"
SLN="$(find . -maxdepth 3 -type f -name '*.sln' | head -n 1 || true)"
if [[ -z "$SLN" ]]; then
  echo "[ERROR] .sln file not found under $INPUT_DIR"
  exit 2
fi

echo "[INFO] Running ReSharper InspectCode"
echo "[INFO] Solution: $SLN"
echo "[INFO] Verbosity: $VERBOSITY"
echo "[INFO] Output: $OUTPUT_DIR/$OUTPUT_FILE"

# Run InspectCode with SARIF output, no profiles
"$INSPECT" "$SLN" \
  --format=Sarif \
  --output="$OUTPUT_DIR/$OUTPUT_FILE" \
  --verbosity="$VERBOSITY"

if [[ -f "$OUTPUT_DIR/$OUTPUT_FILE" ]]; then
  echo "[INFO] SARIF saved to $OUTPUT_DIR/$OUTPUT_FILE"
else
  echo "[WARN] SARIF was not created"
fi
