"""Top-level command dispatch for pipeline execution providers."""

from __future__ import annotations

from collections.abc import Callable

from pipeline.config_utils import AnalyzersConfigHelper
from pipeline.dast.cli import run as run_dast

ExecutionCommand = Callable[..., object]

_EXECUTION_COMMANDS: dict[str, ExecutionCommand] = {
    "dast": run_dast,
}


def dispatch_execution_command(
    arguments: list[str],
    *,
    analyzer_config: AnalyzersConfigHelper,
) -> bool:
    """Dispatch a catalog-declared standalone execution subcommand.

    Returning ``False`` leaves legacy SAST argument parsing to the caller. A command is
    reachable only when both the common catalog and the executor registry declare it.
    """
    if not arguments:
        return False

    execution_type = arguments[0].lower()
    if execution_type not in analyzer_config.get_standalone_execution_types():
        return False

    command = _EXECUTION_COMMANDS.get(execution_type)
    if command is None:
        raise ValueError(f"No command handler is registered for {execution_type}")

    provider = analyzer_config.get_execution_provider(execution_type)
    if provider.get("name") != execution_type:
        raise ValueError(f"The {execution_type} execution provider must use the same catalog name")

    command(arguments[1:], analyzer_config=analyzer_config)
    return True
