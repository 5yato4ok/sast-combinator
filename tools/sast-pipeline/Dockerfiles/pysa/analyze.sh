#!/usr/bin/env bash
set -euo pipefail
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
mkdir -p "$OUTPUT_DIR"
echo "[INFO] Pysa: analyzing $INPUT_DIR"
cd "$INPUT_DIR"

if [[ ! -f ".pyre_configuration" ]]; then
  echo "[INFO] Creating minimal .pyre_configuration"
  cat > .pyre_configuration <<'JSON'
{
  "source_directories": [ "." ],
  "taint_models_path": []
}
JSON
fi

set +e
pyre analyze --no-verify --save-results-to "${OUTPUT_DIR}/pysa.json" 2>&1 | tee "${OUTPUT_DIR}/pysa.log"
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  echo "[WARN] Pysa finished with non-zero status ($rc). See pysa.log"
fi
echo "[INFO] Results at ${OUTPUT_DIR}/pysa.json"
