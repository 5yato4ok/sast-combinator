from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pipeline.cli as pipeline_cli
import yaml
from pipeline.cli import dispatch_execution_command
from pipeline.config_utils import AnalyzersConfigHelper
from pipeline.dast.cli import run as run_dast
from pipeline.dast.contracts import (
    DastConnectorOutcome,
    DastConnectorOutcomeState,
    DastRecoveryState,
    DastRunState,
    DastTerminalResult,
    DastTransportMetadata,
)
from pipeline.dast.executor import DastExecutionResult, DastExecutionTelemetry
from pipeline.execution import execute_pipeline
from pipeline.registry import ExecutionProvider, ExecutionProviderRegistry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "pipeline/config/analyzers.yaml"


def _dast_declaration():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return next(analyzer for analyzer in config["analyzers"] if analyzer.get("name") == "dast")


def test_dast_remains_in_common_analyzer_catalog_as_standalone_execution():
    declaration = _dast_declaration()

    assert declaration == {
        "name": "dast",
        "commentary": (
            "Standalone DAST gateway execution. This common-catalog entry is dispatched only through "
            "pipeline.dast.DastExecutor and is excluded from SAST source/build/analyzer fan-in."
        ),
        "type": "standalone",
        "execution_type": "dast",
        "image": "aist-dast-connector:v2",
        "enabled": True,
        "time_class": "slow",
        "output_type": "DAST Autonomous Scan",
        "result_file": "dast_result.json",
        "language": [
            "c",
            "cpp",
            "csharp",
            "go",
            "java",
            "javascript",
            "kotlin",
            "objc",
            "php",
            "python",
            "ruby",
            "rust",
            "scala",
            "swift",
            "terraform",
            "typescript",
        ],
    }


def test_sast_catalog_views_and_filters_never_select_standalone_dast():
    helper = AnalyzersConfigHelper(CONFIG_PATH)

    assert "dast" not in helper.get_supported_analyzers()
    assert "aist-dast-connector:v2" not in helper.get_all_images()
    assert (
        helper.get_filtered_analyzers(
            ["dast"],
            max_time_class="slow",
            non_compile_project=True,
        )
        == []
    )


def test_catalog_has_no_legacy_dast_analyzer_transport_fields():
    serialized = yaml.safe_dump(_dast_declaration())

    assert "sast-dast" not in serialized
    assert "DAST_GATEWAY_URL" not in serialized
    assert "DAST_INTEGRATOR_TOKEN" not in serialized
    assert "integrations/v1" not in serialized


def test_canonical_execution_dispatch_resolves_dast_image_from_common_catalog(monkeypatch):
    calls = []

    class FakeExecutor:
        def __init__(self, *, connector_image, result_file):
            # The catalog says which image to run; how that image is built is the connector's own
            # business, because it packages this package's code rather than a third-party tool.
            calls.append(("catalog", connector_image, result_file))

        def execute(self, execution):
            calls.append(("execution", execution))
            return "typed-result"

    monkeypatch.setattr("pipeline.execution.DastExecutor", FakeExecutor)
    execution = SimpleNamespace(pipeline_id="pipeline-123")

    result = execute_pipeline("dast", execution, analyzer_config=AnalyzersConfigHelper(CONFIG_PATH))

    assert result == "typed-result"
    assert calls == [
        ("catalog", "aist-dast-connector:v2", "dast_result.json"),
        ("execution", execution),
    ]


def test_dast_command_uses_canonical_dispatch_without_sast_builder(monkeypatch, tmp_path, capsys):
    command_file = tmp_path / "command.json"
    command_file.write_text(
        """{
          "contract_version": "2.0",
          "idempotency_key": "launch-123",
          "correlation_id": "pipeline-123",
          "target_id": "cloud-backend",
          "capability_revision": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "trigger": {"repository_key": "backend", "type": "GIT_HASH", "ref": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
          "parameters": {"depth": "light"}
        }""",
        encoding="utf-8",
    )
    token_file = tmp_path / "token"
    token_file.write_text("public.secret", encoding="utf-8")
    token_file.chmod(0o600)
    terminal_result = DastTerminalResult(
        run_id="run-123",
        status=DastRunState.SUCCEEDED,
        selection={"stand_id": "qa", "relation": "exact", "distance": 0},
        trigger_resolution=None,
        dast_run_metadata=DastTransportMetadata(source_commits={"backend": "b" * 40}),
        report={"findings": []},
    )
    recovery = DastRecoveryState(
        correlation_id="pipeline-123",
        idempotency_key="launch-123",
        run_id="run-123",
    )
    result = DastExecutionResult(
        outcome=DastConnectorOutcome(state=DastConnectorOutcomeState.TERMINAL, recovery=recovery),
        terminal_result=terminal_result,
        recovery=recovery,
        telemetry=DastExecutionTelemetry.empty(),
    )
    executions = []
    monkeypatch.setattr(
        "pipeline.dast.cli.execute_pipeline",
        lambda execution_type, execution, *, analyzer_config: (
            executions.append((execution_type, execution, analyzer_config)) or result
        ),
    )

    catalog = AnalyzersConfigHelper(CONFIG_PATH)
    run_dast(
        [
            "--pipeline-id",
            "pipeline-123",
            "--gateway-url",
            "https://dast.internal",
            "--command-file",
            str(command_file),
            "--workspace",
            str(tmp_path / "workspace"),
            "--output-dir",
            str(tmp_path / "output"),
            "--token-file",
            str(token_file),
        ],
        analyzer_config=catalog,
    )

    assert len(executions) == 1
    assert executions[0][0] == "dast"
    assert executions[0][1].command.idempotency_key == "launch-123"
    assert executions[0][2] is catalog
    assert '"run_id":"run-123"' in capsys.readouterr().out


def test_common_cli_dispatches_catalog_declared_dast_command(monkeypatch):
    command = Mock()
    registry = ExecutionProviderRegistry(
        ExecutionProvider(
            execution_type="dast",
            metric_label="dast",
            operations=frozenset({"execute"}),
            execute=Mock(),
            command=command,
        ),
    )
    monkeypatch.setattr(
        pipeline_cli,
        "build_execution_registry",
        lambda **_kwargs: registry,
    )
    catalog = AnalyzersConfigHelper(CONFIG_PATH)

    handled = dispatch_execution_command(["dast", "--pipeline-id", "pipeline-123"], analyzer_config=catalog)

    assert handled is True
    command.assert_called_once_with(
        ["--pipeline-id", "pipeline-123"],
        analyzer_config=catalog,
    )


def test_run_pipeline_has_no_dast_specific_side_dispatch():
    source = (PROJECT_ROOT / "run_pipeline.py").read_text(encoding="utf-8")

    assert "dispatch_execution_command(arguments, analyzer_config=ANALYZERS_CONFIG)" in source
    assert "pipeline.dast" not in source
    assert 'arguments[:1] == ["dast"]' not in source
