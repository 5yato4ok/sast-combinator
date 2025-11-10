#!/bin/bash
set -e

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
REPORT_DIR="${OUTPUT_DIR}/codechecker-reports"
JSON_PATH="${OUTPUT_DIR}/${3:-codechecker_result.json}"

# Determine quiet options for apt-get based on LOG_LEVEL
LOG_LEVEL="${LOG_LEVEL:-INFO}"
if [[ "${LOG_LEVEL}" != "DEBUG" ]]; then
    APT_OPTS="-qq"
else
    APT_OPTS=""
fi

echo "[INFO] Checking..."

if [ -f "$COMPILE_COMMANDS_PATH" ]; then
    echo "[INFO] Compile commands exist: $COMPILE_COMMANDS_PATH"
else
    echo "[WARNING] Compile commands not exist: $COMPILE_COMMANDS_PATH"
    exit 2
fi

if [[ ! -x "$COMPILER_PATH" ]]; then
    echo "[WARNING] Compiler not found or not executable: $COMPILER_PATH"
    exit 2
fi

echo "[INFO] Setting up environment."

COMPILER_DIR="$(dirname "$COMPILER_PATH")"

# Add compiler directory to PATH if not already included
if [[ ":$PATH:" != *":$COMPILER_DIR:"* ]]; then
    export PATH="$COMPILER_DIR:$PATH"
    echo "[INFO] Added to PATH: $COMPILER_DIR"
else
    echo "[INFO] Compiler directory already in PATH: $COMPILER_DIR"
fi

COMPILER_NAME="$(basename "$COMPILER_PATH")"

if "$COMPILER_PATH" --version 2>/dev/null | grep -qi "clang"; then
    echo "[INFO] Compiler '$COMPILER_NAME' is a Clang-based compiler"
else
    echo "[ERROR] Compiler '$COMPILER_NAME' is not Clang — installing system Clang..."
    apt-get update ${APT_OPTS} && apt-get install -y ${APT_OPTS} clang-17
    COMPILER_PATH="$(command -v clang++)"
    COMPILER_DIR="$(dirname "$COMPILER_PATH")"
fi

# Extract Clang major version
CLANG_VERSION_RAW=$("$COMPILER_PATH" --version | grep -o 'clang version [0-9]\+' | awk '{print $3}')
if [[ -z "$CLANG_VERSION_RAW" ]]; then
    echo "[WARNING] Unable to detect Clang version."
    exit 1
fi

echo "[INFO] Detected Clang version: $CLANG_VERSION_RAW"

# Check if diagtool exists in PATH
if ! command -v diagtool &> /dev/null; then
    echo "[ERROR] diagtool not found."
    echo "[INFO] Installing clang-tools-$CLANG_VERSION_RAW, llvm-$CLANG_VERSION_RAW and clang-tidy-$CLANG_VERSION_RAW..."

    # Add LLVM APT repository if not already present
    if ! grep -q "apt.llvm.org" /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null; then
        echo "[INFO] Adding LLVM APT repository..."

        apt-get update ${APT_OPTS}
        apt-get install ${APT_OPTS} -y wget gnupg lsb-release software-properties-common

        wget -qO - https://apt.llvm.org/llvm-snapshot.gpg.key | apt-key add -
        echo "deb http://apt.llvm.org/$(lsb_release -cs)/ llvm-toolchain-$(lsb_release -cs)-$CLANG_VERSION_RAW main" \
            > /etc/apt/sources.list.d/llvm.list
    fi

    apt-get update ${APT_OPTS}
    apt-get install ${APT_OPTS} -y "clang-tools-$CLANG_VERSION_RAW" "llvm-$CLANG_VERSION_RAW" "clang-tidy-$CLANG_VERSION_RAW"

    echo "[INFO] Installed clang-tools-$CLANG_VERSION_RAW, clang-tidy-$CLANG_VERSION_RAW and llvm-$CLANG_VERSION_RAW."
else
    echo "[INFO] diagtool already available: $(command -v diagtool)"
fi

# Symlink required tools to compiler directory
for tool in diagtool clang-check scan-build scan-view clang-tidy; do
    BIN_PATH="/usr/lib/llvm-$CLANG_VERSION_RAW/bin/$tool"
    LINK_PATH="$COMPILER_DIR/$tool"

    if [[ -f "$BIN_PATH" ]]; then
        if [[ ! -f "$LINK_PATH" ]]; then
            ln -s "$BIN_PATH" "$LINK_PATH"
            echo "[INFO] Symlinked $tool -> $LINK_PATH"
        else
            echo "[INFO] $tool already symlinked in compiler directory"
        fi
    else
        echo "[ERROR] $tool not found at $BIN_PATH"
    fi
done

echo "[INFO] Running CodeChecker on: $COMPILE_COMMANDS_PATH"
echo "[INFO] Output will be saved to: $REPORT_DIR"

mkdir -p "$REPORT_DIR"

if CodeChecker analyze "$COMPILE_COMMANDS_PATH" --output "$REPORT_DIR"; then
    echo "[INFO] CodeChecker analyze completed with no critical issues."
else
    echo "[ERROR] CodeChecker found issues or exited with non-zero status (possibly 3)."
fi

echo "[INFO] CodeChecker analysis complete."

echo "[INFO] Generating JSON report: $JSON_PATH"

if CodeChecker parse -e json --trim-path-prefix "$INPUT_DIR" -o "$JSON_PATH" "$REPORT_DIR"; then
    echo "[INFO] CodeChecker parse completed with no critical issues."
else
    echo "[ERROR] CodeChecker parse found issues or exited with non-zero status (possibly 2)."
fi
