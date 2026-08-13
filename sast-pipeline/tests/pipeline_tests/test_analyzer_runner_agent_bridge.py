"""Tests for the agent-bridge analyzer-type behavior in ``run_selected_analyzers``.

Inside the builder container, agent-bridge analyzers MUST be skipped. Their
bridge runs on the host orchestrator after the builder container completes.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import yaml

import pipeline.analyzer_runner as ar


def _write_config(tmp_path: Path, analyzers: list[dict]) -> str:
    config_path = tmp_path / "analyzers.yaml"
    config_path.write_text(yaml.safe_dump({"analyzers": analyzers}), encoding="utf-8")
    return str(config_path)


def _patch_no_docker(monkeypatch):
    """Stub out every Docker side-effect so the loop is testable in-process."""
    monkeypatch.setattr(ar, "run_docker", MagicMock())
    monkeypatch.setattr(ar.docker_utils, "image_exists", lambda name: True)
    monkeypatch.setattr(ar.docker_utils, "build_image", MagicMock())
    monkeypatch.setattr(ar.docker_utils, "run_pipeline_container", MagicMock())
    monkeypatch.setattr(ar.docker_utils, "collect_git_metadata", lambda path: {})


def test_agent_bridge_is_skipped_no_docker_calls(tmp_path, monkeypatch):
    _patch_no_docker(monkeypatch)
    config_path = _write_config(tmp_path, [
        {
            "name": "claude-diff-security",
            "type": "agent-bridge",
            "enabled": True,
            "time_class": "slow",
            "skill_name": "aist-diff-security-review",
            "result_file": "claude-diff-security_result.json",
        },
    ])

    output_dir = str(tmp_path / "out")
    project_path = str(tmp_path / "proj")
    os.makedirs(project_path, exist_ok=True)

    ar.run_selected_analyzers(
        config_path=config_path,
        pipeline_id="pipe-agent-skip",
        project_path=project_path,
        output_dir=output_dir,
        builder_container="",
    )

    ar.docker_utils.build_image.assert_not_called()
    ar.run_docker.assert_not_called()


def test_other_analyzer_types_still_run(tmp_path, monkeypatch):
    """A docker analyzer next to an agent-bridge one MUST still be launched."""
    _patch_no_docker(monkeypatch)
    config_path = _write_config(tmp_path, [
        {
            "name": "claude-diff-security",
            "type": "agent-bridge",
            "enabled": True,
            "time_class": "fast",
            "skill_name": "aist-diff-security-review",
            "result_file": "claude-diff-security_result.json",
        },
        {
            "name": "cppcheck",
            "type": "simple",
            "image": "sast-cppcheck",
            "enabled": True,
            "time_class": "fast",
            "language": ["cpp"],
            "output_type": "SARIF",
        },
    ])

    ar.run_selected_analyzers(
        config_path=config_path,
        pipeline_id="pipe-agent-mixed",
        project_path=str(tmp_path),
        output_dir=str(tmp_path / "out"),
        builder_container="builder-x",
    )

    ar.run_docker.assert_called_once()
