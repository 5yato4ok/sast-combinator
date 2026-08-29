"""Canonical library execution dispatch for every registered provider."""

from __future__ import annotations

from pathlib import Path

from pipeline.config_utils import AnalyzersConfigHelper
from pipeline.dast.executor import DastExecutionInput, DastExecutionResult, DastExecutor
from pipeline.registry import ExecutionProvider, ExecutionProviderRegistry
from pipeline.sast_execution import SastExecutionInput, execute_sast

DAST_EXECUTION_TYPE = "dast"
SAST_EXECUTION_TYPE = "sast"
_DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "config" / "analyzers.yaml"


def _dast_handler(catalog: AnalyzersConfigHelper):
    def execute(execution: DastExecutionInput) -> DastExecutionResult:
        provider = catalog.get_execution_provider(DAST_EXECUTION_TYPE)
        if provider.get("name") != DAST_EXECUTION_TYPE or provider.get("type") != "standalone":
            detail = "The DAST catalog provider must be named dast and use standalone execution"
            raise ValueError(detail)
        connector_image = provider.get("image")
        if not isinstance(connector_image, str) or not connector_image:
            detail = "The DAST catalog provider must declare a connector image"
            raise ValueError(detail)
        result_file = catalog.get_analyzer_result_file_name(provider)
        return DastExecutor(connector_image=connector_image, result_file=result_file).execute(execution)

    return execute


def build_execution_registry(
    *,
    analyzer_config: AnalyzersConfigHelper | None = None,
    dast_command=None,
) -> ExecutionProviderRegistry:
    catalog = analyzer_config or AnalyzersConfigHelper(_DEFAULT_CATALOG_PATH)
    return ExecutionProviderRegistry(
        ExecutionProvider(
            execution_type=SAST_EXECUTION_TYPE,
            metric_label="sast",
            operations=frozenset({"execute", "cancel"}),
            execute=execute_sast,
        ),
        ExecutionProvider(
            execution_type=DAST_EXECUTION_TYPE,
            metric_label="dast",
            operations=frozenset({"execute", "cancel", "resume"}),
            execute=_dast_handler(catalog),
            command=dast_command,
        ),
    )


def execute_pipeline(
    execution_type: str,
    execution: DastExecutionInput | SastExecutionInput,
    *,
    analyzer_config: AnalyzersConfigHelper | None = None,
    registry: ExecutionProviderRegistry | None = None,
) -> DastExecutionResult | object:
    """Resolve and execute through the single provider registry."""
    resolved_registry = registry or build_execution_registry(analyzer_config=analyzer_config)
    return resolved_registry.resolve(execution_type).execute(execution)
