#!/bin/sh
set -eu

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-eslint_security_result.sarif}"

mkdir -p "$OUTPUT_DIR"

# Create a minimal ESLint config if none present
TMP_ESLINTRC="/tmp/.eslintrc.json"
if [ ! -f "$INPUT_DIR/.eslintrc.json" ] && [ ! -f "$INPUT_DIR/.eslintrc.js" ] && [ ! -f "$INPUT_DIR/.eslintrc.cjs" ]; then
  cat > "$TMP_ESLINTRC" <<'JSON'
{
  "root": true,
  "parser": "@typescript-eslint/parser",
  "plugins": [
    "@typescript-eslint",
    "security",
    "no-unsanitized",
    "security-node"
  ],
  "extends": [
    "plugin:@typescript-eslint/recommended"
  ],
  "env": { "es6": true, "node": true, "browser": true },
  "rules": {
    "security/detect-eval-with-expression": "warn",
    "security/detect-unsafe-regex": "warn",
    "security/detect-non-literal-regexp": "warn",
    "security/detect-non-literal-fs-filename": "warn",
    "no-unsanitized/method": "warn",
    "no-unsanitized/property": "warn"
  },
  "overrides": [
    {
      "files": ["**/*.ts", "**/*.tsx"],
      "parser": "@typescript-eslint/parser",
      "plugins": ["@typescript-eslint"]
    }
  ]
}
JSON
  ESLINT_ARGS="--config $TMP_ESLINTRC"
else
  ESLINT_ARGS=""
fi

# Lint JS/TS and output SARIF
npx --yes eslint "$INPUT_DIR" \
  --ext .js,.jsx,.ts,.tsx \
  --format @microsoft/eslint-formatter-sarif \
  $ESLINT_ARGS > "$OUTPUT_FILE"|| {
    echo "[WARN] ESLint returned non-zero. Probably found something."
}

echo "[INFO] ESLint security+taint results at $OUTPUT_FILE"
