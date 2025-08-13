#!/bin/bash
set -e

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
REPORT_DIR="${OUTPUT_DIR}/codechecker-reports"
JSON_PATH="${OUTPUT_DIR}/flawfinder_result.json"

echo "[+] Checking..."

if [ -f "$COMPILE_COMMANDS_PATH" ]; then
    echo "[+] Compile commands exist: $COMPILE_COMMANDS_PATH"
else
    echo "[x] Compile commands not exist: $COMPILE_COMMANDS_PATH"
    exit 2
fi

if [[ ! -x "$COMPILER_PATH" ]]; then
    echo "[x] Compiler not found or not executable: $COMPILER_PATH"
    exit 2
fi

echo "[+] Setting up environment."

COMPILER_DIR="$(dirname "$COMPILER_PATH")"

# Add compiler directory to PATH if not already included
if [[ ":$PATH:" != *":$COMPILER_DIR:"* ]]; then
    export PATH="$COMPILER_DIR:$PATH"
    echo "[+] Added to PATH: $COMPILER_DIR"
else
    echo "[✓] Compiler directory already in PATH: $COMPILER_DIR"
fi

COMPILER_NAME="$(basename "$COMPILER_PATH")"

if "$COMPILER_PATH" --version 2>/dev/null | grep -qi "clang"; then
    echo "[✓] Compiler '$COMPILER_NAME' is a Clang-based compiler"
else
    echo "[!] Compiler '$COMPILER_NAME' is not Clang — installing system Clang..."
    apt-get update && apt-get install -y clang-17
    COMPILER_PATH="$(command -v clang++)"
    COMPILER_DIR="$(dirname "$COMPILER_PATH")"
fi

# Extract Clang major version
CLANG_VERSION_RAW=$("$COMPILER_PATH" --version | grep -o 'clang version [0-9]\+' | awk '{print $3}')
if [[ -z "$CLANG_VERSION_RAW" ]]; then
    echo "[x] Unable to detect Clang version."
    exit 1
fi

echo "[+] Detected Clang version: $CLANG_VERSION_RAW"

# Check if diagtool exists in PATH
if ! command -v diagtool &> /dev/null; then
    echo "[!] diagtool not found."
    echo "[+] Installing clang-tools-$CLANG_VERSION_RAW, llvm-$CLANG_VERSION_RAW and clang-tidy-$CLANG_VERSION_RAW..."

    # Add LLVM APT repository if not already present
    if ! grep -q "apt.llvm.org" /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null; then
        echo "[+] Adding LLVM APT repository..."

        apt-get update
        apt-get install -y wget gnupg lsb-release software-properties-common

        wget -qO - https://apt.llvm.org/llvm-snapshot.gpg.key | apt-key add -
        echo "deb http://apt.llvm.org/$(lsb_release -cs)/ llvm-toolchain-$(lsb_release -cs)-$CLANG_VERSION_RAW main" \
            > /etc/apt/sources.list.d/llvm.list
    fi

    apt-get update
    apt-get install -y "clang-tools-$CLANG_VERSION_RAW" "llvm-$CLANG_VERSION_RAW" "clang-tidy-$CLANG_VERSION_RAW"

    echo "[✓] Installed clang-tools-$CLANG_VERSION_RAW, clang-tidy-$CLANG_VERSION_RAW and llvm-$CLANG_VERSION_RAW."
else
    echo "[✓] diagtool already available: $(command -v diagtool)"
fi

# Symlink required tools to compiler directory
for tool in diagtool clang-check scan-build scan-view clang-tidy; do
    BIN_PATH="/usr/lib/llvm-$CLANG_VERSION_RAW/bin/$tool"
    LINK_PATH="$COMPILER_DIR/$tool"

    if [[ -f "$BIN_PATH" ]]; then
        if [[ ! -f "$LINK_PATH" ]]; then
            ln -s "$BIN_PATH" "$LINK_PATH"
            echo "[+] Symlinked $tool -> $LINK_PATH"
        else
            echo "[✓] $tool already symlinked in compiler directory"
        fi
    else
        echo "[!] $tool not found at $BIN_PATH"
    fi
done

echo "[+] Running CodeChecker on: $COMPILE_COMMANDS_PATH"
echo "[+] Output will be saved to: $REPORT_DIR"

mkdir -p "$REPORT_DIR"

if CodeChecker analyze "$COMPILE_COMMANDS_PATH" --output "$REPORT_DIR"; then
    echo "[✓] CodeChecker analyze completed with no critical issues."
else
    echo "[!] CodeChecker found issues or exited with non-zero status (possibly 2)."
fi

echo "[✓] CodeChecker analysis complete."

echo "[+] Generating JSON report: $JSON_PATH"

if CodeChecker parse -e json --trim-path-prefix "$INPUT_DIR" -o "$JSON_PATH" "$REPORT_DIR"; then
    echo "[✓] CodeChecker parse completed with no critical issues."
else
    echo "[!] CodeChecker parse found issues or exited with non-zero status (possibly 2)."
fi
