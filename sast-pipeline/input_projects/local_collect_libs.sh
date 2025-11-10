#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${1:-}"

PROJECT_DIR="${PROJECT_ROOT}"
DOTNET_INSTALL_DIR="${PROJECT_DIR}/.dotnet"
PACKAGES_DIR="${PROJECT_DIR}/.nuget_packages"
DOTNET_VERSION="${DOTNET_VERSION:-8.0.400}"

export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export DOTNET_CLI_TELEMETRY_OPTOUT=1

cd "${PROJECT_DIR}"

# Install local .NET SDK
curl -sSL https://dot.net/v1/dotnet-install.sh -o dotnet-install.sh
chmod +x dotnet-install.sh

echo "[INFO] Installing .NET SDK ${DOTNET_VERSION} -> ${DOTNET_INSTALL_DIR}"
./dotnet-install.sh --version "${DOTNET_VERSION}" --install-dir "${DOTNET_INSTALL_DIR}" --no-path

export PATH="${DOTNET_INSTALL_DIR}:${PATH}"

# Restore NuGet packages
mkdir -p "${PACKAGES_DIR}"
cd "${PROJECT_DIR}"
dotnet restore --runtime linux-x64 --packages "${PACKAGES_DIR}"
#dotnet build --no-restore

echo
echo "[DONE] Document analyses-service is ready at: ${PROJECT_DIR}"
echo "  - .NET SDK: ${DOTNET_INSTALL_DIR} (version: $(${DOTNET_INSTALL_DIR}/dotnet --version))"
echo "  - NuGet cache: ${PACKAGES_DIR}"
