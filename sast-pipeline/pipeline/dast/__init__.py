"""Public surface of the DAST package.

The package holds two halves with different deployment scopes. ``contracts`` and the
connector run *inside* the connector container image, which ships a deliberately minimal
slice of ``pipeline``. ``executor`` and ``cli`` are host-side orchestration and pull in
Docker and catalog machinery that image does not contain -- yet they live in this package,
so the image copies them anyway.

Importing them eagerly here made ``python -m pipeline.dast.connector`` load the host half
before the connector's own module, so any host-only import in ``executor`` crashed the
container at startup. They are therefore resolved on first attribute access instead: the
host sees an unchanged ``from pipeline.dast import DastExecutor``, and the container never
touches them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pipeline.dast.contracts import (
    DastConnectorOutcomeState,
    DastRecoveryState,
    DastStartCommand,
    DastTerminalResult,
)

if TYPE_CHECKING:
    from pipeline.dast.executor import (
        DastExecutionIncomplete,
        DastExecutionInput,
        DastExecutionLocalFailure,
        DastExecutionResult,
        DastExecutionTelemetry,
        DastExecutor,
    )

_EXECUTOR_EXPORTS = frozenset({
    "DastExecutionIncomplete",
    "DastExecutionInput",
    "DastExecutionLocalFailure",
    "DastExecutionResult",
    "DastExecutionTelemetry",
    "DastExecutor",
})

__all__ = [
    "DastExecutionInput",
    "DastExecutionIncomplete",
    "DastExecutionLocalFailure",
    "DastExecutionResult",
    "DastExecutionTelemetry",
    "DastExecutor",
    "DastConnectorOutcomeState",
    "DastRecoveryState",
    "DastStartCommand",
    "DastTerminalResult",
]


def __getattr__(name: str) -> Any:
    if name in _EXECUTOR_EXPORTS:
        # Deliberately not a module-level import: deferring it is the whole mechanism, and a
        # top-level one would put the host half back on the connector's import path.
        from pipeline.dast import executor

        return getattr(executor, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    return sorted(__all__)
