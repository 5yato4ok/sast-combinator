"""
Lock the `dast` analyzer entry in pipeline/config/analyzers.yaml.

Analyzers are data, not code: the SAST orchestrator iterates this file to know what to
launch. A typo here silently disables the analyzer (or drops it from the language filter)
in production, so we pin the schema in a test — mirrors test_analyzers_yaml_agent_bridge.py's
pattern for the claude-* entries.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

CONFIG_PATH = (
    Path(__file__).resolve().parents[2]
    / "pipeline"
    / "config"
    / "analyzers.yaml"
)

DOCKERFILE_DIR = (
    Path(__file__).resolve().parents[2]
    / "Dockerfiles"
    / "dast"
)


def _load_analyzer(name: str) -> dict:
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    for analyzer in data.get("analyzers", []):
        if analyzer.get("name") == name:
            return analyzer
    pytest.fail(f"{name} entry missing from analyzers.yaml")
    return {}  # unreachable, satisfies type checkers


@pytest.fixture(scope="module")
def dast_analyzer():
    return _load_analyzer("dast")


def test_type_is_simple(dast_analyzer):
    # Launches through the standard analyzer_runner Docker flow, not agent-bridge —
    # the DAST run itself happens on a separate VM via the integration gateway.
    assert dast_analyzer["type"] == "simple"


def test_image_name(dast_analyzer):
    assert dast_analyzer["image"] == "sast-dast"


def test_enabled_by_default(dast_analyzer):
    assert dast_analyzer["enabled"] is True


def test_time_class_is_slow(dast_analyzer):
    # A real DAST run can take a long time — never scheduled under the fast/medium budgets.
    assert dast_analyzer["time_class"] == "slow"


def test_output_type_uses_dedicated_dast_scan_type(dast_analyzer):
    # Dedicated scan_type (not the generic "Generic Findings Import" bucket) so DAST findings
    # route through canonical dedupe — see aist/dedupe/custom.py's SUPPORTED_SCAN_TYPES and
    # aist/parser_overrides.py's DastReportParser/install_dast_parser, same pattern as the
    # claude-* entries' dedicated scan types.
    assert dast_analyzer["output_type"] == "DAST Autonomous Scan"


def test_result_filename(dast_analyzer):
    assert dast_analyzer["result_file"] == "dast_result.json"


def test_language_list_is_all_languages_like_claude_entries(dast_analyzer):
    # DAST tests the deployed target, not any one source language — the filter must never
    # drop this analyzer for a project regardless of its detected languages.
    expected = {
        "c", "cpp", "csharp", "go", "java", "javascript", "kotlin", "objc",
        "php", "python", "ruby", "rust", "scala", "swift", "terraform", "typescript",
    }
    assert set(dast_analyzer["language"]) == expected


def test_required_env_vars_listed(dast_analyzer):
    env = set(dast_analyzer.get("env") or [])
    for name in (
        "DAST_GATEWAY_URL", "DAST_INTEGRATOR_TOKEN", "DAST_TARGET",
        "DAST_TIER", "DAST_DEPTH", "PROJECT_VERSION", "PIPELINE_ID",
    ):
        assert name in env, f"missing env var: {name!r}"


def test_dockerfile_and_analyze_script_exist():
    assert (DOCKERFILE_DIR / "Dockerfile").is_file()
    analyze_sh = DOCKERFILE_DIR / "analyze.sh"
    assert analyze_sh.is_file()


def test_analyze_script_has_three_arg_entrypoint_convention():
    # Same INPUT_DIR/OUTPUT_DIR/OUTPUT_FILE positional convention every other `simple`
    # analyzer's analyze.sh uses (see Dockerfiles/semgrep/analyze.sh, snyk/analyze.sh).
    content = (DOCKERFILE_DIR / "analyze.sh").read_text(encoding="utf-8")
    assert 'INPUT_DIR="${1:-/workspace}"' in content
    assert 'OUTPUT_DIR="${2:-/shared/output}"' in content
    assert "${3:-dast_result.json}" in content


def test_analyze_script_no_ops_cleanly_when_dast_not_configured(tmp_path):
    """
    Real behavior test (not just a static content check): run the actual analyze.sh with no
    DAST_GATEWAY_URL/DAST_INTEGRATOR_TOKEN set (the common case — most projects have no DAST
    integration configured) and confirm it exits 0 with an empty-but-valid findings envelope,
    never attempting a network call. Doesn't need Docker — analyze.sh is plain bash+curl+jq.
    """
    input_dir = tmp_path / "workspace"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    output_file_name = "dast_result.json"

    env = {k: v for k, v in os.environ.items() if not k.startswith("DAST_")}
    result = subprocess.run(
        ["/bin/bash", str(DOCKERFILE_DIR / "analyze.sh"), str(input_dir), str(output_dir), output_file_name],
        env=env, capture_output=True, text=True, timeout=30, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "not configured" in result.stdout
    output_path = output_dir / output_file_name
    assert output_path.is_file()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload == {"name": "DAST", "type": "DAST Autonomous Scan", "findings": []}


def test_analyze_script_treats_409_as_non_fatal_busy(tmp_path):
    """
    A busy gateway (another run already in progress) must not fail the pipeline — the analyzer
    surfaces a clear [INFO] line and writes an empty findings set instead. Faked via a stub
    `curl` on PATH rather than a real network call: the stub answers /ping with 200 and /runs
    with 409, matching the shapes analyze.sh actually parses (-w "%{http_code}" appended to the
    body, so the stub must do the same).
    """
    input_dir = tmp_path / "workspace"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()

    stub_bin = tmp_path / "stubbin"
    stub_bin.mkdir()
    stub_curl = stub_bin / "curl"
    stub_curl.write_text(
        "#!/bin/bash\n"
        'url="${@: -1}"\n'
        "out=''\n"
        'args=("$@")\n'
        'for i in "${!args[@]}"; do\n'
        '  if [[ "${args[$i]}" == "-o" ]]; then out="${args[$((i+1))]}"; fi\n'
        "done\n"
        'if [[ "$url" == *"/integrations/v1/ping" ]]; then\n'
        "  [[ -n \"$out\" ]] && echo '{\"pong\":true}' > \"$out\"\n"
        "  echo -n '200'\n"
        'elif [[ "$url" == *"/integrations/v1/runs" ]]; then\n'
        "  [[ -n \"$out\" ]] && echo '{\"error\":\"busy\"}' > \"$out\"\n"
        "  echo -n '409'\n"
        "fi\n",
        encoding="utf-8",
    )
    stub_curl.chmod(0o755)

    env = {k: v for k, v in os.environ.items() if not k.startswith("DAST_")}
    env["PATH"] = f"{stub_bin}:{env.get('PATH', '')}"
    env["DAST_GATEWAY_URL"] = "https://dast-gateway.invalid"
    env["DAST_INTEGRATOR_TOKEN"] = "pub.secret"  # noqa: S105
    env["DAST_TARGET"] = "cp-backend"
    env["DAST_TIER"] = "test"
    env["DAST_DEPTH"] = "light"

    result = subprocess.run(
        ["/bin/bash", str(DOCKERFILE_DIR / "analyze.sh"), str(input_dir), str(output_dir), "dast_result.json"],
        env=env, capture_output=True, text=True, timeout=30, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "DAST busy" in result.stdout
    payload = json.loads((output_dir / "dast_result.json").read_text(encoding="utf-8"))
    assert payload == {"name": "DAST", "type": "DAST Autonomous Scan", "findings": []}
