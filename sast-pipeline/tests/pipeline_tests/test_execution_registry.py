from types import SimpleNamespace

import pytest

from pipeline.contracts import (
    ExecutionArtifact,
    ExecutionInput,
    ExecutionOutcome,
    RecoveryCheckpoint,
)
from pipeline.execution import execute_pipeline
from pipeline.registry import ExecutionProvider, ExecutionProviderRegistry
from pipeline.sast_execution import SastExecutionInput, execute_sast


def test_public_contracts_have_deterministic_secret_free_wire_values():
    checkpoint = RecoveryCheckpoint(values={"cursor": 7, "run_id": "provider-run"})
    execution = ExecutionInput(
        execution_id="opaque-caller-id",
        execution_type="DAST",
        payload={"target": "api", "depth": "deep"},
        checkpoint=checkpoint,
    )
    outcome = ExecutionOutcome(
        state="terminal",
        artifacts=(ExecutionArtifact(kind="report", path="result.json", media_type="application/json"),),
        checkpoint=checkpoint,
    )

    assert execution.to_wire() == {
        "checkpoint": {"values": {"cursor": 7, "run_id": "provider-run"}, "version": 1},
        "execution_id": "opaque-caller-id",
        "execution_type": "dast",
        "payload": {"depth": "deep", "target": "api"},
    }
    assert outcome.to_wire()["artifacts"] == [
        {"kind": "report", "media_type": "application/json", "path": "result.json"},
    ]
    assert "token" not in str(execution.to_wire()).lower()


def test_registry_is_the_library_dispatch_boundary_for_fake_providers():
    calls = []
    registry = ExecutionProviderRegistry(
        ExecutionProvider(
            execution_type="fake",
            metric_label="fake",
            operations=frozenset({"execute"}),
            execute=lambda value: calls.append(value) or "bounded-result",
        ),
    )

    result = execute_pipeline("FAKE", {"input": True}, registry=registry)

    assert result == "bounded-result"
    assert calls == [{"input": True}]
    with pytest.raises(ValueError, match="No execution provider"):
        execute_pipeline("missing", {}, registry=registry)


def test_registry_rejects_duplicate_and_catalog_only_providers():
    provider = ExecutionProvider(
        execution_type="fake",
        metric_label="fake",
        operations=frozenset({"execute"}),
        execute=lambda value: value,
    )
    with pytest.raises(ValueError, match="Duplicate execution provider"):
        ExecutionProviderRegistry(provider, provider)

    registry = ExecutionProviderRegistry(provider)
    catalog = SimpleNamespace(get_standalone_execution_types=lambda: ["fake"])
    with pytest.raises(ValueError, match="must match exactly"):
        registry.validate_catalog(catalog)


def test_sast_facade_always_cleans_up_its_execution(monkeypatch, tmp_path):
    cleanup = []
    monkeypatch.setattr(
        "pipeline.sast_execution.configure_project_run_analyses",
        lambda **arguments: {"output_dir": arguments["output_dir"]},
    )
    monkeypatch.setattr(
        "pipeline.sast_execution.cleanup_pipeline_containers",
        cleanup.append,
    )
    execution = SastExecutionInput(
        execution_id="sast-execution",
        runtime_arguments={"pipeline_id": "sast-execution", "output_dir": str(tmp_path / "result")},
    )

    result = execute_sast(execution)

    assert result.launch_data == {"output_dir": str(tmp_path / "result")}
    assert cleanup == ["sast-execution"]
