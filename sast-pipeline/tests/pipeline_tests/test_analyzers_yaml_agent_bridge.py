"""
Lock the agent-bridge analyzer entries in pipeline/config/analyzers.yaml.

Analyzers are data, not code: the SAST orchestrator iterates this file
to know what to launch. A typo here silently disables an analyzer in
production, so we pin the schema in a test.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

CONFIG_PATH = (
    Path(__file__).resolve().parents[2]
    / "pipeline"
    / "config"
    / "analyzers.yaml"
)


def _load_analyzer(name: str) -> dict:
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    for analyzer in data.get("analyzers", []):
        if analyzer.get("name") == name:
            return analyzer
    pytest.fail(f"{name} entry missing from analyzers.yaml")
    return {}  # unreachable, satisfies type checkers


@pytest.fixture(scope="module")
def diff_analyzer():
    return _load_analyzer("claude-diff-security")


@pytest.fixture(scope="module")
def full_analyzer():
    return _load_analyzer("claude-full-security")


def test_type_is_agent_bridge(diff_analyzer):
    assert diff_analyzer["type"] == "agent-bridge"


def test_skill_name_matches_skill_md_directory(diff_analyzer):
    assert diff_analyzer["skill_name"] == "aist-diff-security-review"


def test_output_type_uses_dedicated_claude_scan_type(diff_analyzer):
    # Maps via aist.internal_upload.resolve_scan_type to the "Claude Diff
    # Security" scan_type whose parser (subclass of GenericParser) the AIST
    # app installs in factory.PARSERS at startup. The dedicated test_type
    # name lets canonical dedupe handle these findings as a first-class
    # scanner instead of the generic catch-all.
    assert diff_analyzer["output_type"] == "Claude Diff Security"


def test_result_filename_matches_skill_contract(diff_analyzer):
    assert diff_analyzer["result_file"] == "claude-diff-security_result.json"


def test_required_result_and_truncation_file_declared(diff_analyzer):
    assert diff_analyzer["required_result"] is True
    assert diff_analyzer["truncation_file"] == "claude-diff-security_truncated.flag"


def test_ai_response_artifact_declared(diff_analyzer):
    ai_response = diff_analyzer["artifacts"]["ai_response"]
    assert ai_response["path"] == "claude-diff-security_ai_response.json"
    assert ai_response["format"] == "aist_ai_finding_response_v1"
    assert ai_response["match_key"] == "unique_id_from_tool"


def test_required_env_vars_listed(diff_analyzer):
    env = set(diff_analyzer.get("env") or [])
    for name in ("BASE_COMMIT", "EXCLUDED_PATHS_JSON", "CLAUDE_DIFF_MAX_FILES", "CLAUDE_DIFF_MAX_BYTES"):
        assert name in env, f"missing env var: {name!r}"


def test_enabled_by_default(diff_analyzer):
    assert diff_analyzer.get("enabled", True) is True


# ----------------------------------------------------------------------- #
# claude-full-security: registered as a sibling agent-bridge analyzer.    #
# Per-pipeline enablement is expressed in launch config; mutex with diff  #
# is intentionally not enforced at this layer (see plan Decisions).       #
# ----------------------------------------------------------------------- #


def test_full_type_is_agent_bridge(full_analyzer):
    assert full_analyzer["type"] == "agent-bridge"


def test_full_skill_name_matches_skill_md_directory(full_analyzer):
    assert full_analyzer["skill_name"] == "aist-full-security-review"


def test_full_output_type_uses_dedicated_claude_scan_type(full_analyzer):
    assert full_analyzer["output_type"] == "Claude Full Security"


def test_full_result_filename_matches_skill_contract(full_analyzer):
    assert full_analyzer["result_file"] == "claude-full-security_result.json"


def test_full_required_result_and_truncation_file_declared(full_analyzer):
    assert full_analyzer["required_result"] is True
    assert full_analyzer["truncation_file"] == "claude-full-security_truncated.flag"


def test_full_ai_response_artifact_declared(full_analyzer):
    ai_response = full_analyzer["artifacts"]["ai_response"]
    assert ai_response["path"] == "claude-full-security_ai_response.json"
    assert ai_response["format"] == "aist_ai_finding_response_v1"
    assert ai_response["match_key"] == "unique_id_from_tool"


def test_full_required_env_vars_listed(full_analyzer):
    env = set(full_analyzer.get("env") or [])
    expected = {
        "EXCLUDED_PATHS_JSON",
        "AGENT_FULL_MAX_FILES",
        "AGENT_FULL_MAX_BYTES",
        "AGENT_FULL_MAX_FILE_BYTES",
        "AGENT_FULL_MAX_FINDINGS",
    }
    missing = expected - env
    assert not missing, f"missing env vars: {sorted(missing)!r}"


def test_full_does_not_consume_base_commit(full_analyzer):
    # Full-scan reasons over the deployable revision as a whole — there is
    # no baseline to diff against, so BASE_COMMIT must not appear.
    env = set(full_analyzer.get("env") or [])
    assert "BASE_COMMIT" not in env


def test_full_enabled_by_default(full_analyzer):
    assert full_analyzer.get("enabled", True) is True


def test_full_time_class_is_slow(full_analyzer):
    # Symmetric with diff so both fall under the same time-budget bucket.
    assert full_analyzer["time_class"] == "slow"


def test_full_language_list_matches_diff(diff_analyzer, full_analyzer):
    # Full security review applies to the same language set as diff — keeping
    # them aligned avoids the trap of one analyzer running on a project where
    # the other is silently skipped.
    assert sorted(full_analyzer["language"]) == sorted(diff_analyzer["language"])


# ----------------------------------------------------------------------- #
# claude-intake-review / claude-intake-diff: supply-chain intake review of #
# untrusted third-party source. Same agent-bridge contract; intake-review  #
# reuses the full-scan budget keys, intake-diff reuses the diff baseline.  #
# ----------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def intake_full_analyzer():
    return _load_analyzer("claude-intake-review")


@pytest.fixture(scope="module")
def intake_diff_analyzer():
    return _load_analyzer("claude-intake-diff")


def test_intake_full_contract(intake_full_analyzer):
    a = intake_full_analyzer
    assert a["type"] == "agent-bridge"
    assert a["skill_name"] == "aist-intake-review"
    assert a["output_type"] == "Claude Intake Review"
    assert a["result_file"] == "claude-intake-review_result.json"
    assert a["required_result"] is True
    assert a["truncation_file"] == "claude-intake-review_truncated.flag"
    assert a.get("enabled", True) is True
    assert a["time_class"] == "slow"
    ai = a["artifacts"]["ai_response"]
    assert ai["path"] == "claude-intake-review_ai_response.json"
    assert ai["format"] == "aist_ai_finding_response_v1"
    assert ai["match_key"] == "unique_id_from_tool"


def test_intake_full_uses_full_budget_keys(intake_full_analyzer):
    env = set(intake_full_analyzer.get("env") or [])
    expected = {
        "EXCLUDED_PATHS_JSON",
        "AGENT_FULL_MAX_FILES",
        "AGENT_FULL_MAX_BYTES",
        "AGENT_FULL_MAX_FILE_BYTES",
        "AGENT_FULL_MAX_FINDINGS",
    }
    assert not (expected - env), f"missing env vars: {sorted(expected - env)!r}"
    # Whole-revision scan — no diff baseline.
    assert "BASE_COMMIT" not in env


def test_intake_diff_contract(intake_diff_analyzer):
    a = intake_diff_analyzer
    assert a["type"] == "agent-bridge"
    assert a["skill_name"] == "aist-intake-diff-review"
    assert a["output_type"] == "Claude Intake Diff"
    assert a["result_file"] == "claude-intake-diff_result.json"
    assert a["required_result"] is True
    assert a["truncation_file"] == "claude-intake-diff_truncated.flag"
    assert a.get("enabled", True) is True
    assert a["time_class"] == "slow"
    ai = a["artifacts"]["ai_response"]
    assert ai["path"] == "claude-intake-diff_ai_response.json"
    assert ai["format"] == "aist_ai_finding_response_v1"
    assert ai["match_key"] == "unique_id_from_tool"


def test_intake_diff_uses_diff_baseline_keys(intake_diff_analyzer):
    env = set(intake_diff_analyzer.get("env") or [])
    expected = {
        "BASE_COMMIT",
        "EXCLUDED_PATHS_JSON",
        "CLAUDE_DIFF_MAX_FILES",
        "CLAUDE_DIFF_MAX_BYTES",
    }
    assert not (expected - env), f"missing env vars: {sorted(expected - env)!r}"


def test_intake_language_lists_match_siblings(diff_analyzer, intake_full_analyzer, intake_diff_analyzer):
    # Intake reviews must run on the same language set as the security
    # analyzers — otherwise a plugin in a given language is silently skipped.
    assert sorted(intake_full_analyzer["language"]) == sorted(diff_analyzer["language"])
    assert sorted(intake_diff_analyzer["language"]) == sorted(diff_analyzer["language"])


def test_intake_result_filenames_distinct_from_security_analyzers():
    # The intake artifacts must not collide with the security analyzers'
    # files in the shared output directory.
    names = {
        _load_analyzer(n)["result_file"]
        for n in (
            "claude-diff-security",
            "claude-full-security",
            "claude-intake-review",
            "claude-intake-diff",
        )
    }
    assert len(names) == 4
