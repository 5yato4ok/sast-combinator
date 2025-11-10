#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${1:-/workspace}"
REPO_URL="${2:-https://github.com/Soham7-dev/AspGoat.git}"
REPO_NAME="${3:-AspGoat}"

PROJECT_DIR="${PROJECT_ROOT}/${REPO_NAME}"
DOTNET_INSTALL_DIR="${PROJECT_DIR}/.dotnet"
PACKAGES_DIR="${PROJECT_DIR}/.nuget_packages"
NATIVE_DIR="${PROJECT_DIR}/native_libs"
DOTNET_VERSION="${DOTNET_VERSION:-8.0.400}"

export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export DOTNET_CLI_TELEMETRY_OPTOUT=1

mkdir -p "${PROJECT_ROOT}"

# Clone or update repository
if [ -d "${PROJECT_DIR}/.git" ]; then
  echo "[INFO] Repository exists, pulling updates..."
  git -C "${PROJECT_DIR}" fetch --depth=1 || true
  git -C "${PROJECT_DIR}" pull --ff-only || true
else
  echo "[INFO] Cloning ${REPO_URL} -> ${PROJECT_DIR}"
  git clone "${REPO_URL}" "${PROJECT_DIR}" --depth 1
fi

cd "${PROJECT_DIR}"

# Install local .NET SDK
curl -sSL https://dot.net/v1/dotnet-install.sh -o dotnet-install.sh
chmod +x dotnet-install.sh

echo "[INFO] Installing .NET SDK ${DOTNET_VERSION} -> ${DOTNET_INSTALL_DIR}"
./dotnet-install.sh --version "${DOTNET_VERSION}" --install-dir "${DOTNET_INSTALL_DIR}" --no-path

export PATH="${DOTNET_INSTALL_DIR}:${PATH}"

# Fetch ICU + OpenSSL 3 native libraries (Debian/Ubuntu best-effort)
mkdir -p "${NATIVE_DIR}" /tmp/aspgoat_dl
pushd /tmp/aspgoat_dl >/dev/null

if command -v apt-get >/dev/null 2>&1; then
  echo "[INFO] Using apt-get to download .deb packages"
  apt-get update -y >/dev/null || true
  apt-get download -y libicu74 || apt-get download -y libicu72 || apt-get download -y libicu70 || true
  apt-get download -y libssl3 || true
  apt-get download -y libcrypto3 || true
else
  echo "[WARN] apt-get not available; native libs will not be downloaded"
fi

shopt -s nullglob
for deb in *.deb; do
  echo "[INFO] Extracting $deb"
  dpkg-deb -x "$deb" "${NATIVE_DIR}"
done
shopt -u nullglob

# Fix symlinks for ICU
LIBDIRS=$(find "${NATIVE_DIR}" -type d \( -path "*/usr/lib/*" -o -path "*/lib/*" \) || true)
for d in $LIBDIRS; do
  [ -d "$d" ] || continue
  for base in icui18n icuuc icudata; do
    sofile=$(ls "$d"/lib${base}.so.* 2>/dev/null | head -n1 || true)
    [ -n "$sofile" ] && ln -sf "$sofile" "$d/lib${base}.so"
  done
done

ARCH="$(uname -m)"
case "$ARCH" in
  aarch64|arm64) LIBSUB="aarch64-linux-gnu" ;;
  x86_64|amd64)  LIBSUB="x86_64-linux-gnu" ;;
  *)             LIBSUB="" ;;
esac

# Add to runtime search path if OpenSSL 3 was found
if [ -n "$LIBSUB" ] && [ -d "${NATIVE_DIR}/usr/lib/${LIBSUB}" ]; then
  export LD_LIBRARY_PATH="${NATIVE_DIR}/usr/lib/${LIBSUB}:${NATIVE_DIR}/usr/lib:${NATIVE_DIR}/lib:${LD_LIBRARY_PATH:-}"
else
  export LD_LIBRARY_PATH="${NATIVE_DIR}/usr/lib:${NATIVE_DIR}/lib:${LD_LIBRARY_PATH:-}"
fi

popd >/dev/null

# Restore NuGet packages
mkdir -p "${PACKAGES_DIR}"
cd "${PROJECT_DIR}"
dotnet restore --packages "${PACKAGES_DIR}"
dotnet build --no-restore

echo
echo "[DONE] AspGoat is ready at: ${PROJECT_DIR}"
echo "  - .NET SDK: ${DOTNET_INSTALL_DIR} (version: $(${DOTNET_INSTALL_DIR}/dotnet --version))"
echo "  - NuGet cache: ${PACKAGES_DIR}"
echo "  - Native libs: ${NATIVE_DIR}"

export DOTNET_PATH=${DOTNET_INSTALL_DIR}
export LIB_PATH=${LD_LIBRARY_PATH}
export PROJECT_PATH=${PROJECT_DIR}
export NON_COMPILE_PROJECT=0
