"""Top-level command dispatch for pipeline execution providers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipeline.dast.cli import run as run_dast
from pipeline.execution import build_execution_registry

if TYPE_CHECKING:
    from pipeline.config_utils import AnalyzersConfigHelper


def dispatch_execution_command(
    arguments: list[str],
    *,
    analyzer_config: AnalyzersConfigHelper,
) -> bool:
    """
    Dispatch a catalog-declared standalone execution subcommand.

    Returning ``False`` leaves legacy SAST argument parsing to the caller. A command is
    reachable only when both the common catalog and the executor registry declare it.
    """
    if not arguments:
        return False

    execution_type = arguments[0].lower()
    if execution_type not in analyzer_config.get_standalone_execution_types():
        return False
    registry = build_execution_registry(analyzer_config=analyzer_config, dast_command=run_dast)
    registry.validate_catalog(analyzer_config)
    provider = registry.resolve(execution_type)
    provider.command(arguments[1:], analyzer_config=analyzer_config)
    return True
