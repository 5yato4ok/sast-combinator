#!/usr/bin/env bash
set -euo pipefail
INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
mkdir -p "$OUTPUT_DIR"
: "${SONAR_HOST_URL:?SONAR_HOST_URL required}"
: "${SONAR_TOKEN:?SONAR_TOKEN required}"
: "${SONAR_PROJECT_KEY:?SONAR_PROJECT_KEY required}"
ORG_OPT=""; if [[ -n "${SONAR_ORGANIZATION:-}" ]]; then ORG_OPT="-Dsonar.organization=${SONAR_ORGANIZATION}"; fi
echo "[INFO] SonarQube: analyzing $INPUT_DIR"
set +e
sonar-scanner -Dsonar.projectKey="${SONAR_PROJECT_KEY}" -Dsonar.host.url="${SONAR_HOST_URL}" -Dsonar.login="${SONAR_TOKEN}" -Dsonar.sources="${INPUT_DIR}" -Dsonar.python.version=3 ${ORG_OPT} ${SONAR_SCANNER_OPTS:-} 2>&1 | tee "${OUTPUT_DIR}/sonarqube-scan.log"
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  echo "[WARN] sonar-scanner exited $rc. See sonarqube-scan.log"
fi
echo "[INFO] Fetching issues via Web API"
set +e
curl -sf -u "${SONAR_TOKEN}:" "${SONAR_HOST_URL}/api/issues/search?componentKeys=${SONAR_PROJECT_KEY}&ps=500" -o "${OUTPUT_DIR}/sonarqube.json"
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  echo "[WARN] Could not fetch issues via API."
fi
echo "[INFO] Results at ${OUTPUT_DIR}/sonarqube.json"
