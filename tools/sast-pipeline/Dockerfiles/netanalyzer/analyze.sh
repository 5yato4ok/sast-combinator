#!/usr/bin/env bash
set -euo pipefail
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-netanalyzers_security.sarif}"
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

TMP_PROPS="$INPUT_DIR/Directory.Build.props"
CLEANUP=0
if [ ! -f "$TMP_PROPS" ]; then
cat > "$TMP_PROPS" <<'XML'
<Project>
  <PropertyGroup>
    <EnableNETAnalyzers>true</EnableNETAnalyzers>
    <AnalysisLevel>latest</AnalysisLevel>
    <!-- Enable Security category, if disabled by default -->
    <CodeAnalysisTreatWarningsAsErrors>false</CodeAnalysisTreatWarningsAsErrors>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.CodeAnalysis.NetAnalyzers" Version="8.*" PrivateAssets="all" />
    <PackageReference Include="SecurityCodeScan.VS2019" Version="5.*" PrivateAssets="all" />
    <PackageReference Include="Meziantou.Analyzer" Version="2.*" PrivateAssets="all" />
  </ItemGroup>
</Project>
XML
CLEANUP=1
fi

dotnet restore "$INPUT_DIR" -v "$DOTNET_V"
dotnet build "$INPUT_DIR" -v "$DOTNET_V" \
  -p:ErrorLog="$OUTPUT_FILE;version=2;SarifVersion=2" || true

[ "$CLEANUP" -eq 1 ] && rm -f "$TMP_PROPS"
echo "[INFO] NetAnalyzers (Security) SARIF -> $OUTPUT_FILE"
