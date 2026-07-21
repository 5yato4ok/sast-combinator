#!/bin/bash
set -u

INPUT_DIR="${1:-/workspace}"
OUTPUT_DIR="${2:-/shared/output}"
OUTPUT_FILE="${OUTPUT_DIR}/${3:-dast_result.json}"

mkdir -p "$OUTPUT_DIR"

# Ignores $INPUT_DIR — DAST tests the deployed target, not the checked-out source. Egress to
# the gateway rides the existing AIST VPN sidecar (--network container:<vpn>, already attached
# to this container by configure_project_run_analyses before this entrypoint runs) — nothing
# DAST-specific needed here for that part.

_empty_findings() {
    # "type" here is cosmetic (analyzers.yaml's output_type + DastReportParser force the
    # final imported Test's scan_type regardless of this field), but kept consistent with it
    # so a raw dast_result.json inspection is never misleading.
    echo '{"name":"DAST","type":"DAST Autonomous Scan","findings":[]}' > "$OUTPUT_FILE"
}

if [[ -z "${DAST_GATEWAY_URL:-}" || -z "${DAST_INTEGRATOR_TOKEN:-}" ]]; then
    echo "[INFO] DAST not configured for this project (no DAST_GATEWAY_URL/DAST_INTEGRATOR_TOKEN) — skipping."
    _empty_findings
    exit 0
fi

: "${DAST_TARGET:?DAST_TARGET is required}"
: "${DAST_TIER:?DAST_TIER is required}"
: "${DAST_DEPTH:?DAST_DEPTH is required}"

GATEWAY_URL="${DAST_GATEWAY_URL%/}"

# The bearer token goes into a curl config file (mode 600), never a `-H`/`-u` argv value —
# argv is readable by anything with visibility into this container's process list
# (`ps -ef`, `/proc/<pid>/cmdline`, `docker top`, host monitoring/APM agents), which a plain
# `curl -H "Authorization: Bearer ..."` would expose the token through.
CURL_CFG=$(mktemp)
chmod 600 "$CURL_CFG"
trap 'rm -f "$CURL_CFG"' EXIT
printf 'header = "Authorization: Bearer %s"\n' "$DAST_INTEGRATOR_TOKEN" > "$CURL_CFG"

# The deployed version is one opaque string either way (a branch name or a commit hash,
# depending on how this project's version was resolved) — the analyzer has no way to tell
# which, so the SAME value is sent for both fields rather than fabricating a distinction
# that doesn't actually exist at this layer.
SOURCE_REF="${PROJECT_VERSION:-unknown}"
RUN_CORRELATION_ID="${PIPELINE_ID:-unknown}"

echo "[INFO] DAST: checking gateway connectivity..."
PING_STATUS=$(curl -s -o /tmp/dast_ping.json -w "%{http_code}" -K "$CURL_CFG" \
    "${GATEWAY_URL}/integrations/v1/ping" 2>/dev/null || echo "000")
if [[ "$PING_STATUS" != "200" ]]; then
    echo "[ERROR] DAST gateway unreachable or auth rejected (HTTP ${PING_STATUS}) — skipping this cycle."
    _empty_findings
    exit 0
fi
echo "[INFO] DAST gateway reachable."

echo "[INFO] DAST: starting run for target=${DAST_TARGET} tier=${DAST_TIER} depth=${DAST_DEPTH}..."
START_BODY=$(jq -n \
    --arg integrator_run_id "$RUN_CORRELATION_ID" \
    --arg target "$DAST_TARGET" \
    --arg tier "$DAST_TIER" \
    --arg depth "$DAST_DEPTH" \
    --arg ref "$SOURCE_REF" \
    '{integrator_run_id:$integrator_run_id, target:$target, tier:$tier, depth:$depth, source:{branch:$ref, commit:$ref}}')
START_STATUS=$(curl -s -o /tmp/dast_start.json -w "%{http_code}" -K "$CURL_CFG" \
    -H "Content-Type: application/json" -X POST -d "$START_BODY" \
    "${GATEWAY_URL}/integrations/v1/runs" 2>/dev/null || echo "000")

if [[ "$START_STATUS" == "409" ]]; then
    echo "[INFO] DAST busy — another run in progress. Skipping this cycle."
    _empty_findings
    exit 0
fi
if [[ "$START_STATUS" != "202" ]]; then
    echo "[ERROR] DAST run start failed (HTTP ${START_STATUS}): $(cat /tmp/dast_start.json)"
    _empty_findings
    exit 0
fi

DAST_RUN_ID=$(jq -r '.dast_run_id' /tmp/dast_start.json)
echo "[INFO] DAST run started: ${DAST_RUN_ID}"

# Cooperative stop propagation (§A6): on SIGTERM (AIST tearing down this pipeline/analyzer via
# stop_pipeline()), best-effort tell the gateway to stop cooperatively too — never abandons the
# DAST-side run mid-flight without at least trying to hand it a clean wind-down signal. This is
# the analyzer's own best-effort forwarding, distinct from an operator directly calling the
# gateway's POST /stop or the DAST-side `dast request-stop` CLI.
_stop_sent=0
on_term() {
    if [[ "$_stop_sent" -eq 0 && -n "${DAST_RUN_ID:-}" ]]; then
        echo "[INFO] DAST: propagating stop to gateway..."
        curl -s -o /dev/null -K "$CURL_CFG" -X POST \
            "${GATEWAY_URL}/integrations/v1/runs/${DAST_RUN_ID}/stop" 2>/dev/null || true
        _stop_sent=1
    fi
}
trap on_term SIGTERM

CURSOR=0
STATUS="running"
while [[ "$STATUS" == "running" ]]; do
    sleep 15

    LOGS_JSON=$(curl -s -K "$CURL_CFG" \
        "${GATEWAY_URL}/integrations/v1/runs/${DAST_RUN_ID}/logs?since=${CURSOR}" 2>/dev/null || echo '{}')
    echo "$LOGS_JSON" | jq -r '.lines[]? // empty'
    CURSOR=$(echo "$LOGS_JSON" | jq -r '.since // 0')

    STATUS_JSON=$(curl -s -K "$CURL_CFG" \
        "${GATEWAY_URL}/integrations/v1/runs/${DAST_RUN_ID}" 2>/dev/null || echo '{}')
    STATUS=$(echo "$STATUS_JSON" | jq -r '.status // "running"')
done

echo "[INFO] DAST run finished with status: ${STATUS}"

echo "[INFO] DAST: fetching results..."
RESULTS_STATUS=$(curl -s -o "$OUTPUT_FILE" -w "%{http_code}" -K "$CURL_CFG" \
    "${GATEWAY_URL}/integrations/v1/runs/${DAST_RUN_ID}/results" 2>/dev/null || echo "000")
if [[ "$RESULTS_STATUS" != "200" ]]; then
    echo "[INFO] DAST: no results file available (HTTP ${RESULTS_STATUS}) — writing an empty findings set."
    _empty_findings
fi

echo "[INFO] DAST analysis complete. Results saved to: $OUTPUT_FILE"
