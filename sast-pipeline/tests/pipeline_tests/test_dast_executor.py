import json
import subprocess
from pathlib import Path

import pytest
import yaml
from pipeline.dast.contracts import (
    DastConnectorOutcome,
    DastConnectorOutcomeState,
    DastRecoveryState,
    DastStartCommand,
)
from pipeline.dast.contracts import CONNECTOR_EXIT_LOCAL_SETUP
from pipeline.dast.executor import DastExecutionInput, DastExecutionLocalFailure, DastExecutor

CONNECTOR_CONTAINER = "sast_aist-dast-connector_v2_pipeline-123"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CAPABILITY_REVISION = f"sha256:{'a' * 64}"
UNPRIVILEGED_UID = 1000


@pytest.fixture(autouse=True)
def _unprivileged_writer_without_docker(monkeypatch):
    """Default every test to the case that needs no privileges and no daemon."""
    monkeypatch.setattr("pipeline.dast.executor.docker_utils.ensure_image", lambda *args, **kwargs: None)
    monkeypatch.setattr("pipeline.dast.executor.docker_utils.image_runtime_user", lambda image: None)
    monkeypatch.setattr("pipeline.dast.executor.os.geteuid", lambda: UNPRIVILEGED_UID)
    monkeypatch.setattr("pipeline.dast.executor.os.getegid", lambda: UNPRIVILEGED_UID)


def _command():
    return DastStartCommand.from_wire(
        {
            "contract_version": "2.0",
            "idempotency_key": "launch-123",
            "correlation_id": "pipeline-123",
            "target_id": "cloud-backend",
            "capability_revision": CAPABILITY_REVISION,
            "trigger": {"repository_key": "backend", "type": "GIT_HASH", "ref": "b" * 40},
            "parameters": {"depth": "light"},
        }
    )


def _terminal_result():
    return {
        "contract_version": "2.0",
        "run_id": "run-123",
        "status": "succeeded",
        "selection": {"stand_id": "qa", "relation": "exact", "distance": 0},
        "trigger_resolution": None,
        "dast_run_metadata": {"source_commits": {"backend": "b" * 40}},
        "report": {"findings": []},
        "audit": {},
    }


def _write_terminal_output(execution, recovery):
    output_dir = execution.workspace / "output"
    (output_dir / "result.json").write_text(json.dumps(_terminal_result()), encoding="utf-8")
    (output_dir / "recovery.json").write_text(json.dumps(recovery.to_wire()), encoding="utf-8")
    outcome = DastConnectorOutcome(state=DastConnectorOutcomeState.TERMINAL, recovery=recovery)
    (output_dir / "outcome.json").write_text(json.dumps(outcome.to_wire()), encoding="utf-8")
    (output_dir / "telemetry.json").write_text(
        json.dumps({"version": 1, "logs_delivered": 3, "max_log_lag_seconds": 1.25}),
        encoding="utf-8",
    )


def _execution(tmp_path, **overrides):
    token_file = tmp_path / "token"
    token_file.write_text("public.secret", encoding="utf-8")
    token_file.chmod(0o600)
    values = {
        "pipeline_id": "pipeline-123",
        "gateway_url": "https://dast.internal",
        "command": _command(),
        "workspace": tmp_path / "execution",
        "token_file": token_file,
        "vpn_container_name": "vpn-pipeline-123",
    }
    values.update(overrides)
    return DastExecutionInput(**values)


def test_executor_uses_shared_container_logging_and_vpn_namespace_without_secret_env(monkeypatch, tmp_path):
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("certificate-material", encoding="utf-8")
    ca_file.chmod(0o600)
    execution = _execution(tmp_path, ca_file=ca_file)
    calls = []

    def run_container(**kwargs):
        calls.append(kwargs)
        _write_terminal_output(execution, DastRecoveryState.initial(execution.command).for_run("run-123"))

    monkeypatch.setattr("pipeline.dast.executor.docker_utils.run_pipeline_container", run_container)

    result = DastExecutor(connector_image="aist-dast-connector:v2").execute(execution)

    assert result.terminal_result.status == "succeeded"
    assert result.outcome.state is DastConnectorOutcomeState.TERMINAL
    assert result.recovery.run_id == "run-123"
    assert result.telemetry.logs_delivered == 3
    assert result.telemetry.max_log_lag_seconds == 1.25
    assert calls == [
        {
            "image": "aist-dast-connector:v2",
            # Built from the package: the Dockerfile lives here and its context is the package
            # root, because the image packages `pipeline.dast` itself.
            "dockerfile_dir": "Dockerfiles/dast_connector",
            "build_context": ".",
            "pipeline_id": "pipeline-123",
            "volumes": {
                str(execution.workspace / "input.json"): "/run/aist/input.json:ro",
                str(execution.workspace / "output"): "/run/aist/output",
                str(execution.token_file): "/run/secrets/dast-token:ro",
                str(ca_file): "/run/secrets/dast-ca.pem:ro",
            },
            "env": None,
            "args": [
                "--input",
                "/run/aist/input.json",
                "--output",
                "/run/aist/output",
                "--token-file",
                "/run/secrets/dast-token",
                "--ca-file",
                "/run/secrets/dast-ca.pem",
                "--trusted-vpn",
            ],
            "network": "container:vpn-pipeline-123",
            "user": f"{UNPRIVILEGED_UID}:{UNPRIVILEGED_UID}",
        },
    ]
    serialized_call = json.dumps(calls)
    assert "public.secret" not in serialized_call
    assert "certificate-material" not in serialized_call
    connector_input = json.loads((execution.workspace / "input.json").read_text(encoding="utf-8"))
    assert connector_input["command"] == execution.command.to_wire()
    assert connector_input["recovery"] == DastRecoveryState.initial(execution.command).to_wire()
    assert "public.secret" not in json.dumps(connector_input)
    assert "certificate-material" not in json.dumps(connector_input)


def test_executor_cleans_up_only_its_own_connector_container_on_interrupt(monkeypatch, tmp_path):
    """Cleaning up by pipeline-id substring also matched ``aist-vpn-<pipeline_id>``, its owner's."""
    execution = _execution(tmp_path)
    cleaned = []
    swept = []
    monkeypatch.setattr(
        "pipeline.dast.executor.docker_utils.run_pipeline_container",
        lambda **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    monkeypatch.setattr("pipeline.dast.executor.docker_utils.cleanup_container", cleaned.append)
    monkeypatch.setattr("pipeline.dast.executor.docker_utils.cleanup_pipeline_containers", swept.append)

    with pytest.raises(KeyboardInterrupt):
        DastExecutor(connector_image="aist-dast-connector:v2").execute(execution)

    assert cleaned == [CONNECTOR_CONTAINER]
    assert swept == []


def test_executor_returns_typed_unreachable_outcome_with_persisted_recovery(monkeypatch, tmp_path):
    recovery = DastRecoveryState.initial(_command()).for_run("run-123").with_cursor(7)
    execution = _execution(tmp_path, recovery=recovery)
    cleaned = []

    def run_container(**_kwargs):
        output_dir = execution.workspace / "output"
        (output_dir / "recovery.json").write_text(json.dumps(recovery.to_wire()), encoding="utf-8")
        raise subprocess.CalledProcessError(1, ["docker", "run"])

    monkeypatch.setattr("pipeline.dast.executor.docker_utils.run_pipeline_container", run_container)
    monkeypatch.setattr("pipeline.dast.executor.docker_utils.cleanup_container", cleaned.append)

    result = DastExecutor(connector_image="aist-dast-connector:v2").execute(execution)

    assert result.outcome.state is DastConnectorOutcomeState.UNREACHABLE
    assert result.recovery == recovery
    assert result.terminal_result is None
    assert cleaned == [CONNECTOR_CONTAINER]


def test_executor_rejects_group_readable_token_file_before_container_start(monkeypatch, tmp_path):
    execution = _execution(tmp_path)
    execution.token_file.chmod(0o640)
    called = []
    monkeypatch.setattr("pipeline.dast.executor.docker_utils.run_pipeline_container", lambda **kwargs: called.append(kwargs))

    with pytest.raises(ValueError, match="group or other"):
        DastExecutor(connector_image="aist-dast-connector:v2").execute(execution)

    assert called == []


def test_executor_hands_the_mounted_files_to_the_image_user_and_keeps_it_unprivileged(monkeypatch, tmp_path):
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("certificate-material", encoding="utf-8")
    ca_file.chmod(0o600)
    execution = _execution(tmp_path, ca_file=ca_file)
    chowned = []
    calls = []

    monkeypatch.setattr("pipeline.dast.executor.os.geteuid", lambda: 0)
    monkeypatch.setattr("pipeline.dast.executor.os.getegid", lambda: 0)
    monkeypatch.setattr("pipeline.dast.executor.docker_utils.image_runtime_user", lambda image: (1001, 1001))
    monkeypatch.setattr("pipeline.dast.executor.os.chown", lambda path, uid, gid: chowned.append((str(path), uid, gid)))

    def run_container(**kwargs):
        calls.append(kwargs)
        _write_terminal_output(execution, DastRecoveryState.initial(execution.command).for_run("run-123"))

    monkeypatch.setattr("pipeline.dast.executor.docker_utils.run_pipeline_container", run_container)

    DastExecutor(connector_image="aist-dast-connector:v2").execute(execution)

    # The container keeps the unprivileged user its image declares; ownership moved to meet it.
    assert calls[0]["user"] is None
    assert chowned == [
        (str(execution.workspace / "input.json"), 1001, 1001),
        (str(execution.workspace / "output"), 1001, 1001),
        (str(execution.token_file), 1001, 1001),
        (str(ca_file), 1001, 1001),
    ]
    assert execution.token_file.stat().st_mode & 0o077 == 0


def test_executor_runs_as_itself_when_it_cannot_hand_over_ownership(monkeypatch, tmp_path):
    execution = _execution(tmp_path)
    chowned = []
    calls = []

    monkeypatch.setattr("pipeline.dast.executor.docker_utils.image_runtime_user", lambda image: (1001, 1001))
    monkeypatch.setattr("pipeline.dast.executor.os.chown", lambda path, uid, gid: chowned.append(path))

    def run_container(**kwargs):
        calls.append(kwargs)
        _write_terminal_output(execution, DastRecoveryState.initial(execution.command).for_run("run-123"))

    monkeypatch.setattr("pipeline.dast.executor.docker_utils.run_pipeline_container", run_container)

    DastExecutor(connector_image="aist-dast-connector:v2").execute(execution)

    assert calls[0]["user"] == f"{UNPRIVILEGED_UID}:{UNPRIVILEGED_UID}"
    assert chowned == []


def test_executor_reports_a_local_setup_failure_instead_of_an_unreachable_provider(monkeypatch, tmp_path):
    execution = _execution(tmp_path)
    cleaned = []

    def run_container(**_kwargs):
        raise subprocess.CalledProcessError(CONNECTOR_EXIT_LOCAL_SETUP, ["docker", "run"])

    monkeypatch.setattr("pipeline.dast.executor.docker_utils.run_pipeline_container", run_container)
    monkeypatch.setattr("pipeline.dast.executor.docker_utils.cleanup_container", cleaned.append)

    with pytest.raises(DastExecutionLocalFailure):
        DastExecutor(connector_image="aist-dast-connector:v2").execute(execution)

    assert cleaned == [CONNECTOR_CONTAINER]


def test_dast_common_catalog_declaration_is_standalone_not_a_sast_analyzer():
    config = yaml.safe_load((PROJECT_ROOT / "pipeline/config/analyzers.yaml").read_text(encoding="utf-8"))
    dast = next(analyzer for analyzer in config["analyzers"] if analyzer.get("name") == "dast")

    assert dast["execution_type"] == "dast"
    assert dast["type"] == "standalone"
    assert dast["image"] == "aist-dast-connector:v2"
    assert "env" not in dast


def test_executor_serializes_explicit_recovery_without_source_or_analyzer_pipeline(monkeypatch, tmp_path):
    recovery = DastRecoveryState.initial(_command()).for_run("run-123").with_cursor(17)
    execution = _execution(tmp_path, recovery=recovery)

    def run_container(**_kwargs):
        _write_terminal_output(execution, recovery)

    monkeypatch.setattr("pipeline.dast.executor.docker_utils.run_pipeline_container", run_container)

    DastExecutor(connector_image="aist-dast-connector:v2").execute(execution)

    connector_input = json.loads((execution.workspace / "input.json").read_text(encoding="utf-8"))
    assert connector_input["recovery"] == recovery.to_wire()
    assert set(connector_input) == {
        "contract_version",
        "gateway_url",
        "command",
        "recovery",
        "deadline_at",
        "stop_requested",
        "harvest_only",
    }
    assert "source" not in connector_input
    assert "analyzers" not in connector_input


def test_executor_rejects_success_without_current_telemetry_artifact(monkeypatch, tmp_path):
    execution = _execution(tmp_path)

    def run_container(**_kwargs):
        recovery = DastRecoveryState.initial(execution.command).for_run("run-123")
        _write_terminal_output(execution, recovery)
        (execution.workspace / "output" / "telemetry.json").unlink()

    monkeypatch.setattr("pipeline.dast.executor.docker_utils.run_pipeline_container", run_container)

    with pytest.raises(ValueError, match="telemetry.json"):
        DastExecutor(connector_image="aist-dast-connector:v2").execute(execution)
