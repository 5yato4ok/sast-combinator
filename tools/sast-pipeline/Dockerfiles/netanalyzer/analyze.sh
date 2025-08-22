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

cd "$INPUT_DIR"
SDKV="$(dotnet --version)"

TMP_PROPS="${INPUT_DIR}/Directory.Build.props"
TMP_TARGETS="${INPUT_DIR}/Directory.Build.targets"
CLEAN_PROPS=0
CLEAN_TARGETS=0

if [[ ! -f "$TMP_PROPS" ]]; then
  cat > "$TMP_PROPS" <<'XML'
<Project>
  <!-- General analyzer settings -->
  <PropertyGroup>
    <EnableNETAnalyzers>true</EnableNETAnalyzers>
    <AnalysisLevel>latest</AnalysisLevel>
    <RunAnalyzersDuringBuild>true</RunAnalyzersDuringBuild>
  </PropertyGroup>

  <!-- Resolve SDK version: NETCoreSdkVersion -> SdkVersion (from script) -> 0.0.0 -->
  <PropertyGroup>
    <_SdkVer>$(NETCoreSdkVersion)</_SdkVer>
    <_SdkVer Condition="'$(_SdkVer)' == ''">$(SdkVersion)</_SdkVer>
    <_SdkVer Condition="'$(_SdkVer)' == ''">0.0.0</_SdkVer>

    <!-- Parse major/minor safely -->
    <_SdkMajor>$([System.Int32]::Parse($(_SdkVer.Split('.')[0])))</_SdkMajor>
    <_SdkMinor>$([System.Int32]::Parse($(_SdkVer.Split('.')[1])))</_SdkMinor>
  </PropertyGroup>

  <!-- SDK >= 7 -->
  <ItemGroup Condition="$(_SdkMajor) &gt;= 7">
    <PackageReference Include="Microsoft.CodeAnalysis.NetAnalyzers" Version="8.*" PrivateAssets="all" />
    <PackageReference Include="SecurityCodeScan.VS2022" Version="5.*" PrivateAssets="all" />
  </ItemGroup>

  <!-- 5 <= SDK < 7 -->
  <ItemGroup Condition="$(_SdkMajor) &gt;= 5 and $(_SdkMajor) &lt; 7">
    <PackageReference Include="Microsoft.CodeAnalysis.NetAnalyzers" Version="6.*" PrivateAssets="all" />
    <PackageReference Include="SecurityCodeScan.VS2019" Version="5.*" PrivateAssets="all" />
  </ItemGroup>

  <!-- SDK < 5 (e.g., 2.1/3.1) -->
  <ItemGroup Condition="$(_SdkMajor) &lt; 5">
    <PackageReference Include="Microsoft.CodeAnalysis.FxCopAnalyzers" Version="3.3.2" PrivateAssets="all" />
    <PackageReference Include="SecurityCodeScan.VS2017" Version="3.5.4" PrivateAssets="all" />
  </ItemGroup>
</Project>
XML
  CLEAN_PROPS=1
fi

if [[ ! -f "$TMP_TARGETS" ]]; then
  cat > "$TMP_TARGETS" <<'XML'
<Project>
  <PropertyGroup>
    <_SdkVer>$(NETCoreSdkVersion)</_SdkVer>
    <_SdkVer Condition="'$(_SdkVer)' == ''">$(SdkVersion)</_SdkVer>
    <_SdkVer Condition="'$(_SdkVer)' == ''">0.0.0</_SdkVer>
    <_SdkMajor>$([System.Int32]::Parse($(_SdkVer.Split('.')[0])))</_SdkMajor>
  </PropertyGroup>

  <!-- For SDK < 5, remove any NetAnalyzers and Meziantou pinned elsewhere -->
  <ItemGroup Condition="'$(_SdkMajor)' != '' and $(_SdkMajor) &lt; 5">
    <PackageReference Remove="Microsoft.CodeAnalysis.NetAnalyzers" />
    <PackageReference Update="Microsoft.CodeAnalysis.NetAnalyzers" Version="" />

    <PackageReference Remove="Meziantou.Analyzer" />
    <!-- Defensive: neutralize any central/explicit pin to 2.x -->
    <PackageReference Update="Meziantou.Analyzer" Version="1.*" />
  </ItemGroup>
</Project>
XML
  CLEAN_TARGETS=1
fi

# Cleanup on exit if we created temp props/targets
cleanup() {
  [[ $CLEAN_PROPS -eq 1 ]] && rm -f "$TMP_PROPS" || true
  [[ $CLEAN_TARGETS -eq 1 ]] && rm -f "$TMP_TARGETS" || true
}
trap cleanup EXIT

# -------- Robust NuGet restore --------
dotnet nuget locals all --clear || true

TMP_NUGET="$(mktemp -t nuget-XXXXXX.config)"
{
  echo '<?xml version="1.0" encoding="utf-8"?>'
  echo '<configuration>'
  echo '  <packageSources>'
  echo '    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />'
  # Optional mirror: export NUGET_MIRROR_URL="https://your-mirror/v3/index.json"
  if [[ -n "${NUGET_MIRROR_URL:-}" ]]; then
    echo "    <add key=\"mirror\" value=\"${NUGET_MIRROR_URL}\" />"
  fi
  echo '  </packageSources>'
  echo '  <config>'
  echo '    <add key="globalPackagesFolder" value="/tmp/nuget-packages" />'
  echo '  </config>'
  echo '  <packageSourceMapping>'
  echo '    <packageSource key="nuget.org">'
  echo '      <package pattern="Microsoft.*" />'
  echo '      <package pattern="System.*" />'
  echo '      <package pattern="SecurityCodeScan.*" />'
  echo '      <package pattern="Meziantou.*" />'
  echo '    </packageSource>'
  if [[ -n "${NUGET_MIRROR_URL:-}" ]]; then
    echo '    <packageSource key="mirror">'
    echo '      <package pattern="*" />'
    echo '    </packageSource>'
  fi
  echo '  </packageSourceMapping>'
  echo '</configuration>'
} > "$TMP_NUGET"



echo "[INFO] Restoring packages (SDK ${SDKV})..."
cd "$INPUT_DIR"
dotnet clean

dotnet restore . \
  --configfile "$TMP_NUGET" \
  --no-cache --disable-parallel -v detailed \
  -p:SdkVersion="${SDK_VERSION}"

echo "[INFO] Building with analyzers → SARIF"
dotnet build . -v "$DOTNET_V" \
  -p:SdkVersion="${SDK_VERSION}" \
  -p:RunAnalyzers=true \
  "-p:ErrorLog=${OUTPUT_FILE};format=Sarif;version=2.1" || true


# -------- Post-check --------
if [[ ! -s "$OUTPUT_FILE" ]]; then
  echo "[WARN] SARIF file is missing or empty: $OUTPUT_FILE"
else
  echo "[INFO] SARIF written to: $OUTPUT_FILE"
fi

# Optional: validate/normalize SARIF if sarif tool is present
if command -v sarif >/dev/null 2>&1; then
  echo "[INFO] Validating SARIF..."
  sarif validate "$OUTPUT_FILE" || true
fi
