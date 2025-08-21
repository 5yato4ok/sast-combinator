#!/usr/bin/env bash
#!/usr/bin/env bash
set -euo pipefail
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-infer_csharp.sarif}"
LOG_LEVEL="${LOG_LEVEL:-progress}"
export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
export PATH="$DOTNET_PATH:$PATH"
export LD_LIBRARY_PATH="${LIB_PATH}:${LD_LIBRARY_PATH-}"

mkdir -p "$OUTPUT_DIR"

LOG_LEVEL="${LOG_LEVEL:-progress}"
lvl="$(echo "$LOG_LEVEL" | tr '[:upper:]' '[:lower:]')"
case "$lvl" in
  errors) DOTNET_V="quiet" ;;
  warnings) DOTNET_V="minimal" ;;
  progress|info) DOTNET_V="normal" ;;
  progress+) DOTNET_V="detailed" ;;
  progress++|progress+++) DOTNET_V="diagnostic" ;;
  debug) DOTNET_V="diagnostic" ;;
  *) DOTNET_V="normal" ;;
esac

PUBLISH_DIR=/tmp/publish
rm -rf "$PUBLISH_DIR" && mkdir -p "$PUBLISH_DIR"
dotnet clean
dotnet restore "$INPUT_DIR" -v "$DOTNET_V"
dotnet publish "$INPUT_DIR" -v "$DOTNET_V" -o "$PUBLISH_DIR"

# 2) Launch Infer#
cd /infersharp
./run_infersharp.sh "$PUBLISH_DIR" --sarif

# 3) Move SARIF to output dir
cp /infersharp/infer-out/infersharp.sarif "$OUTPUT_FILE" || \
  (echo "[WARN] SARIF report not found, creating empty"; echo '{"runs":[]}' > "$OUTPUT_FILE")

echo "[INFO] Infer# SARIF -> $OUTPUT_FILE"
