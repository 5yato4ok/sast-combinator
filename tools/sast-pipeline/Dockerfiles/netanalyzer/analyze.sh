#!/usr/bin/env bash
set -euo pipefail
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-netanalyzers_security.sarif}"
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

TMP_PROPS="$INPUT_DIR/Directory.Build.props"
CLEANUP=0
if [ ! -f "$TMP_PROPS" ]; then
  echo "[INFO] Creating file ${TMP_PROPS}"
cat > "$TMP_PROPS" <<'XML'
<Project>
  <!-- General analyzer settings -->
  <PropertyGroup>
    <EnableNETAnalyzers>true</EnableNETAnalyzers>
    <AnalysisLevel>latest</AnalysisLevel>
    <RunAnalyzersDuringBuild>true</RunAnalyzersDuringBuild>
  </PropertyGroup>

  <!-- Resolve the SDK version actually used by MSBuild (from PATH / global.json) -->
  <PropertyGroup>
    <_SdkVer>$(NETCoreSdkVersion)</_SdkVer>
    <_SdkVer Condition="'$(_SdkVer)' == ''">0.0.0</_SdkVer>
  </PropertyGroup>

  <!-- Pick NetAnalyzers package version dynamically based on the SDK version -->
  <PropertyGroup>
    <NetAnalyzersVersion>6.*</NetAnalyzersVersion>
    <NetAnalyzersVersion Condition="$([MSBuild]::VersionGreaterThanOrEquals('$(_SdkVer)','7.0.0'))">7.*</NetAnalyzersVersion>
    <NetAnalyzersVersion Condition="$([MSBuild]::VersionGreaterThanOrEquals('$(_SdkVer)','8.0.0'))">8.*</NetAnalyzersVersion>
  </PropertyGroup>

  <!-- If you prefer to rely on the SDK's built-in analyzers only, remove this block -->
  <ItemGroup>
    <PackageReference Include="Microsoft.CodeAnalysis.NetAnalyzers"
                      Version="$(NetAnalyzersVersion)"
                      PrivateAssets="all" />
  </ItemGroup>

  <!-- SecurityCodeScan: select the package compatible with the current SDK -->
  <ItemGroup Condition="$([MSBuild]::VersionGreaterThanOrEquals('$(_SdkVer)','7.0.0'))">
    <!-- Modern SDKs → VS2022 package (new Roslyn) -->
    <PackageReference Include="SecurityCodeScan.VS2022" Version="5.*" PrivateAssets="all" />
  </ItemGroup>

  <ItemGroup Condition="!$([MSBuild]::VersionGreaterThanOrEquals('$(_SdkVer)','7.0.0'))">
    <!-- Older SDKs → VS2019 package (old Roslyn) -->
    <PackageReference Include="SecurityCodeScan.VS2019" Version="5.*" PrivateAssets="all" />
  </ItemGroup>
</Project>
XML
CLEANUP=1
fi

cd "$INPUT_DIR"
SDKV="$(dotnet --version)"
dotnet clean || true
dotnet restore . -v "$DOTNET_V"
dotnet build "$INPUT_DIR" -v "$DOTNET_V" \
  -p:SdkVersion="$SDKV" \
  -p:RunAnalyzers=true \
  -p:ErrorLog="${OUTPUT_FILE},BuildOutput.sarif,version=2.1" || true

[ "$CLEANUP" -eq 1 ] && rm -f "$TMP_PROPS"
echo "[INFO] NetAnalyzers (Security) SARIF -> $OUTPUT_FILE"
