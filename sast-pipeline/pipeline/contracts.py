"""Django-free public execution contracts owned by ``sast-pipeline``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


def _json_object(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        detail = "Execution contract payload must be a mapping"
        raise TypeError(detail)
    return {str(key): value[key] for key in sorted(value)}


@dataclass(frozen=True, slots=True)
class ExecutionArtifact:
    kind: str
    path: str
    media_type: str = "application/octet-stream"

    def to_wire(self) -> dict[str, str]:
        return {"kind": self.kind, "media_type": self.media_type, "path": self.path}


@dataclass(frozen=True, slots=True)
class RecoveryCheckpoint:
    version: int = 1
    values: Mapping[str, Any] = field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        return {"values": _json_object(self.values), "version": self.version}


@dataclass(frozen=True, slots=True)
class ExecutionInput:
    execution_id: str
    execution_type: str
    payload: Mapping[str, Any]
    checkpoint: RecoveryCheckpoint | None = None

    def __post_init__(self) -> None:
        if not self.execution_id.strip() or not self.execution_type.strip():
            detail = "Execution id and type must not be blank"
            raise ValueError(detail)

    def to_wire(self) -> dict[str, Any]:
        return {
            "checkpoint": self.checkpoint.to_wire() if self.checkpoint else None,
            "execution_id": self.execution_id,
            "execution_type": self.execution_type.lower(),
            "payload": _json_object(self.payload),
        }


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    state: str
    artifacts: tuple[ExecutionArtifact, ...] = ()
    checkpoint: RecoveryCheckpoint | None = None
    detail_code: str = ""

    def to_wire(self) -> dict[str, Any]:
        return {
            "artifacts": [artifact.to_wire() for artifact in self.artifacts],
            "checkpoint": self.checkpoint.to_wire() if self.checkpoint else None,
            "detail_code": self.detail_code,
            "state": self.state,
        }
