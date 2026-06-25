"""Tests for ``pipeline.agent_bridge_runner``."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import yaml

import pipeline.agent_bridge_runner as abr


def _write_config(tmp_path: Path, analyzers: list[dict]) -> str:
    cfg_path = tmp_path / "analyzers.yaml"
    cfg_path.write_text(yaml.safe_dump({"analyzers": analyzers}), encoding="utf-8")
    return str(cfg_path)


def _make_client(success: bool = True) -> MagicMock:
    client = MagicMock()
    if success:
        client.analyze_sync.return_value = {"status": "success", "detail": ""}
    else:
        client.analyze_sync.return_value = {"status": "error", "detail": "boom"}
    return client


def _agent(name: str = "claude-diff-security", **overrides) -> dict:
    data = {
        "name": name,
        "type": "agent-bridge",
        "enabled": True,
        "skill_name": "aist-diff-security-review",
        "result_file": f"{name}_result.json",
        "required_result": True,
        "artifacts": {
            "ai_response": {
                "path": f"{name}_ai_response.json",
                "format": "aist_ai_finding_response_v1",
                "match_key": "unique_id_from_tool",
            },
        },
    }
    data.update(overrides)
    return data


def test_invokes_client_writes_runtime_sidecar_and_returns_success_outcome(tmp_path):
    cfg = _write_config(tmp_path, [_agent()])
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "claude-diff-security_result.json").write_text("{}", encoding="utf-8")

    client = _make_client()
    runtime_env = {
        "BASE_COMMIT": "abc1234",
        "EXCLUDED_PATHS_JSON": '["vendor/", "third_party/"]',
    }

    outcomes = abr.run_agent_bridge_analyzers(
        bridge_client=client,
        config_path=cfg,
        pipeline_id="pipe-1",
        project_path="/tmp/proj",
        output_dir=str(output_dir),
        runtime_env=runtime_env,
    )

    client.analyze_sync.assert_called_once()
    kwargs = client.analyze_sync.call_args.kwargs
    assert kwargs["skill_name"] == "aist-diff-security-review"
    assert kwargs["project_id"] == "pipe-1"
    assert kwargs["source_path"] == "/tmp/proj"
    extra_args = kwargs["extra_args"]
    assert "output_path=" + str(output_dir) in extra_args
    assert "result_filename=claude-diff-security_result.json" in extra_args
    assert "ai_response_filename=claude-diff-security_ai_response.json" in extra_args
    assert "runtime_filename=claude-diff-security_runtime.json" in extra_args

    runtime_path = output_dir / "claude-diff-security_runtime.json"
    assert json.loads(runtime_path.read_text(encoding="utf-8")) == runtime_env
    assert outcomes[0]["status"] == "success"
    assert outcomes[0]["degraded"] is False
    assert outcomes[0]["result_exists"] is True


def test_model_from_config_is_forwarded_to_bridge(tmp_path):
    cfg = _write_config(tmp_path, [_agent(model="opus")])
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "claude-diff-security_result.json").write_text("{}", encoding="utf-8")

    client = _make_client()
    abr.run_agent_bridge_analyzers(
        bridge_client=client,
        config_path=cfg,
        pipeline_id="pipe-1",
        project_path="/tmp/proj",
        output_dir=str(output_dir),
    )

    assert client.analyze_sync.call_args.kwargs["model"] == "opus"


def test_missing_model_in_config_forwards_empty_string(tmp_path):
    cfg = _write_config(tmp_path, [_agent()])  # no model key
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "claude-diff-security_result.json").write_text("{}", encoding="utf-8")

    client = _make_client()
    abr.run_agent_bridge_analyzers(
        bridge_client=client,
        config_path=cfg,
        pipeline_id="pipe-1",
        project_path="/tmp/proj",
        output_dir=str(output_dir),
    )

    assert client.analyze_sync.call_args.kwargs["model"] == ""


def test_required_result_missing_after_success_returns_missing_result_outcome(tmp_path):
    cfg = _write_config(tmp_path, [_agent()])
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    outcomes = abr.run_agent_bridge_analyzers(
        bridge_client=_make_client(),
        config_path=cfg,
        pipeline_id="p",
        project_path="/x",
        output_dir=str(output_dir),
    )

    assert outcomes[0]["status"] == "missing_result"
    assert outcomes[0]["degraded"] is True
    assert outcomes[0]["messages"][0]["code"] == "missing_result"


def test_truncation_marker_returns_truncated_outcome(tmp_path):
    cfg = _write_config(tmp_path, [_agent(truncation_file="diff_truncated.flag")])
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "claude-diff-security_result.json").write_text("{}", encoding="utf-8")
    (output_dir / "diff_truncated.flag").write_text("too large", encoding="utf-8")

    outcomes = abr.run_agent_bridge_analyzers(
        bridge_client=_make_client(),
        config_path=cfg,
        pipeline_id="p",
        project_path="/x",
        output_dir=str(output_dir),
    )

    assert outcomes[0]["status"] == "truncated"
    assert outcomes[0]["degraded"] is True
    assert outcomes[0]["messages"][0]["code"] == "truncated"


def test_skips_non_agent_bridge_analyzers(tmp_path):
    cfg = _write_config(tmp_path, [
        {"name": "cppcheck", "type": "simple", "enabled": True, "image": "sast-cppcheck"},
    ])
    client = _make_client()
    outcomes = abr.run_agent_bridge_analyzers(
        bridge_client=client,
        config_path=cfg,
        pipeline_id="p",
        project_path="/x",
        output_dir=str(tmp_path / "out"),
    )

    assert outcomes == []
    client.analyze_sync.assert_not_called()


def test_disabled_agent_bridge_entry_is_skipped(tmp_path):
    cfg = _write_config(tmp_path, [_agent(enabled=False)])
    client = _make_client()
    outcomes = abr.run_agent_bridge_analyzers(
        bridge_client=client,
        config_path=cfg,
        pipeline_id="p",
        project_path="/x",
        output_dir=str(tmp_path / "out"),
    )

    assert outcomes == []
    client.analyze_sync.assert_not_called()


def test_missing_skill_name_returns_failed_outcome(tmp_path):
    cfg = _write_config(tmp_path, [_agent(skill_name="")])
    outcomes = abr.run_agent_bridge_analyzers(
        bridge_client=_make_client(),
        config_path=cfg,
        pipeline_id="p",
        project_path="/x",
        output_dir=str(tmp_path / "out"),
    )

    assert outcomes[0]["status"] == "failed"
    assert outcomes[0]["degraded"] is True
    assert outcomes[0]["messages"][0]["code"] == "missing_skill_name"


def test_bridge_error_status_returns_failed_outcome(tmp_path):
    cfg = _write_config(tmp_path, [_agent()])
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    outcomes = abr.run_agent_bridge_analyzers(
        bridge_client=_make_client(success=False),
        config_path=cfg,
        pipeline_id="p",
        project_path="/x",
        output_dir=str(output_dir),
    )

    assert outcomes[0]["status"] == "failed"
    assert outcomes[0]["degraded"] is True
    assert outcomes[0]["messages"][0]["code"] == "bridge_error"
    assert "boom" in outcomes[0]["messages"][0]["text"]


def test_bridge_exception_does_not_stop_next_agent(tmp_path):
    cfg = _write_config(tmp_path, [
        _agent("agent-a", skill_name="skill-a"),
        _agent("agent-b", skill_name="skill-b"),
    ])
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    client = MagicMock()
    client.analyze_sync.side_effect = [RuntimeError("bridge down"), {"status": "success"}]

    outcomes = abr.run_agent_bridge_analyzers(
        bridge_client=client,
        config_path=cfg,
        pipeline_id="p",
        project_path="/x",
        output_dir=str(output_dir),
    )

    assert client.analyze_sync.call_count == 2
    assert outcomes[0]["status"] == "failed"
    assert outcomes[0]["messages"][0]["code"] == "bridge_exception"
    assert outcomes[1]["status"] == "missing_result"


def test_missing_config_file_returns_no_outcomes(tmp_path):
    outcomes = abr.run_agent_bridge_analyzers(
        bridge_client=_make_client(),
        config_path=str(tmp_path / "missing.yaml"),
        pipeline_id="p",
        project_path="/x",
        output_dir=str(tmp_path / "out"),
    )

    assert outcomes == []


def test_extra_args_drops_values_with_newline(tmp_path):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    cfg = _write_config(tmp_path, [
        _agent(
            "agent-bad",
            artifacts={
                "ai_response": {
                    "path": "good\nname.json",
                    "format": "aist_ai_finding_response_v1",
                    "match_key": "unique_id_from_tool",
                },
            },
        ),
    ])
    client = _make_client()
    abr.run_agent_bridge_analyzers(
        bridge_client=client,
        config_path=cfg,
        pipeline_id="p",
        project_path="/x",
        output_dir=str(output_dir),
    )

    extra_args = client.analyze_sync.call_args.kwargs["extra_args"]
    assert "good\nname" not in extra_args
    assert "ai_response_filename=" not in extra_args


def test_derive_ai_response_filename_handles_non_standard_suffix():
    assert abr._derive_ai_response_filename("foo_result.json") == "foo_ai_response.json"
    assert abr._derive_ai_response_filename("custom.json") == "custom_ai_response.json"
