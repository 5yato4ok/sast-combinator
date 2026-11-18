"""Library-first SAST execution facade built from existing runtime primitives."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Any

from pipeline.build_configuration import SastRuntimeConfiguration
from pipeline.docker_utils import cleanup_pipeline_containers
from pipeline.project_builder import configure_project_run_analyses

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class SastExecutionInput:
    execution_id: str
    runtime_arguments: SastRuntimeConfiguration


@dataclass(frozen=True, slots=True)
class SastExecutionResult:
    launch_data: Mapping[str, Any]


def execute_sast(execution: SastExecutionInput) -> SastExecutionResult:
    configuration = execution.runtime_arguments
    if configuration.pipeline_id != execution.execution_id:
        detail = "SAST runtime pipeline_id must match the public execution id"
        raise ValueError(detail)
    try:
        return SastExecutionResult(
            launch_data=configure_project_run_analyses(**{
                field.name: getattr(configuration, field.name) for field in fields(configuration)
            }),
        )
    finally:
        cleanup_pipeline_containers(execution.execution_id)
