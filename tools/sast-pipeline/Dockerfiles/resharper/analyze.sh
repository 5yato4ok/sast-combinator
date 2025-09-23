#!/bin/sh
set -eu

# Positional args: INPUT_DIR OUTPUT_DIR OUTPUT_FILE
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
TMP_OUTPUT="full_resharper_result.sarif"
OUTPUT_FILE="${3:-resharper.sarif}"

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
    debug)     VERBOSITY="VERBOSE" ;;
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
dotnet clean

TARGET="$(find . -maxdepth 3 -type f \( -name '*.sln' -o -name '*.csproj' -o -name '*.vbproj' \) | head -n 1 || true)"
if [ -z "$TARGET" ]; then
  echo "[ERROR] .sln file not found under $INPUT_DIR"
  exit 2
fi

# ---------- TEMP INJECTION of Roslyn analyzers (transactional) ----------
TMP_ROOT="$(mktemp -d -p "${TMPDIR:-/tmp}" rs_inject.XXXXXX)"
DBP_PATH="$INPUT_DIR/Directory.Build.props"
NC_PATH="$INPUT_DIR/nuget.config"
BACKUP_DBP=""
BACKUP_NC=""

cleanup() {
  # restore backups or remove temporaries
  [ -n "$BACKUP_DBP" ] && { mv "$DBP_PATH.__backup__" "$DBP_PATH" 2>/dev/null || true; } || rm -f "$DBP_PATH"
  [ -n "$BACKUP_NC"  ] && { mv "$NC_PATH.__backup__" "$NC_PATH"     2>/dev/null || true; } || rm -f "$NC_PATH"
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT INT TERM

# Backup existing files if present
if [ -f "$DBP_PATH" ]; then BACKUP_DBP="1"; mv "$DBP_PATH" "$DBP_PATH.__backup__"; fi
if [ -f "$NC_PATH"  ]; then BACKUP_NC="1";  mv "$NC_PATH"  "$NC_PATH.__backup__";  fi

# Detect SDK major (fallback to 8)
SDK_VER="$(dotnet --version 2>/dev/null || echo 8.0.0)"
SDK_MAJ="$(printf '%s' "$SDK_VER" | cut -d. -f1)"
[ -z "$SDK_MAJ" ] && SDK_MAJ="8"

# Create a minimal nuget.config pointing at nuget.org
cat > "$NC_PATH" <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <clear />
    <add key="nuget" value="https://api.nuget.org/v3/index.json" protocolVersion="3" />
  </packageSources>
</configuration>
EOF

{
  echo '<Project>'
  echo '  <PropertyGroup>'
  echo '    <EnableNETAnalyzers>true</EnableNETAnalyzers>'
  echo '    <AnalysisLevel>latest</AnalysisLevel>'
  echo '    <RunAnalyzers>true</RunAnalyzers>'
  echo '  </PropertyGroup>'
  echo '  <ItemGroup>'
  echo '    <PackageReference Include="SonarAnalyzer.CSharp" Version="9.*" PrivateAssets="all" />'
  echo '    <PackageReference Include="SecurityCodeScan.VS2019" Version="5.6.7" PrivateAssets="all" />'
  echo '    <PackageReference Include="Microsoft.CodeAnalysis.NetAnalyzers" Version="7.*" PrivateAssets="all" />'
  echo '  </ItemGroup>'
  echo '</Project>'
} > "$DBP_PATH"

# Restore with injected analyzers (no repo changes)
echo "[INFO] dotnet --info"
dotnet --info || true

echo "[INFO] dotnet restore (with temporary analyzers)"
# restore at the solution level when possible
SLNDIR="$(dirname "$TARGET")"
dotnet restore "$SLNDIR" --configfile "$NC_PATH"

echo "[INFO] Running ReSharper InspectCode"
echo "[INFO] Project file: $TARGET"
echo "[INFO] Verbosity: $VERBOSITY"
echo "[INFO] Output: $OUTPUT_DIR/$TMP_OUTPUT"

echo "[INFO] Inspections to launch"
"$INSPECT" --dumpIssuesTypes \
  --format=xml \
  --output=$OUTPUT_DIR/resharper-inspections.xml

# Run InspectCode with SARIF output, no profiles
"$INSPECT" "$TARGET" \
  --format=Sarif \
  --properties="RunAnalyzers=true" \
  --output="$OUTPUT_DIR/$TMP_OUTPUT" \
  --verbosity="$VERBOSITY"

if [ -f "$OUTPUT_DIR/$TMP_OUTPUT" ]; then
  echo "[INFO] SARIF saved to $OUTPUT_DIR/$TMP_OUTPUT"
  python3 /filter_sarif.py --dotsettings /profile.DotSettings \
      --input "$OUTPUT_DIR/$TMP_OUTPUT" \
      --output "$OUTPUT_DIR/$OUTPUT_FILE" \
      --prune-rules
else
  echo "[WARN] SARIF was not created"
fi
