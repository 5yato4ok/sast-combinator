"""Canonical execution dispatch for providers declared in the shared analyzer catalog."""

from __future__ import annotations

from pathlib import Path

from pipeline.config_utils import AnalyzersConfigHelper
from pipeline.dast.executor import DastExecutionInput, DastExecutionResult, DastExecutor

DAST_EXECUTION_TYPE = "dast"
_DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "config" / "analyzers.yaml"


def execute_pipeline(
    execution_type: str,
    execution: DastExecutionInput,
    *,
    analyzer_config: AnalyzersConfigHelper | None = None,
) -> DastExecutionResult:
    """Resolve a standalone execution provider from the shared catalog and run it."""
    normalized_type = execution_type.lower()
    if normalized_type != DAST_EXECUTION_TYPE:
        raise ValueError(f"Unsupported standalone pipeline execution type: {normalized_type}")
    catalog = analyzer_config or AnalyzersConfigHelper(_DEFAULT_CATALOG_PATH)
    provider = catalog.get_execution_provider(normalized_type)
    if provider.get("name") != DAST_EXECUTION_TYPE or provider.get("type") != "standalone":
        raise ValueError("The DAST catalog provider must be named dast and use standalone execution")
    connector_image = provider.get("image")
    if not isinstance(connector_image, str) or not connector_image:
        raise ValueError("The DAST catalog provider must declare a connector image")
    return DastExecutor(connector_image=connector_image).execute(execution)
