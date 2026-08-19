"""Strict typed boundaries for the DAST integration gateway v2 protocol."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

CONTRACT_VERSION = "2.0"
# The connector exits with this instead of 1 when it never reached the provider: a bad input file,
# an unusable token, an unwritable output directory. The caller must not retry those -- the next
# attempt runs against the same host state and fails identically. (sysexits.h EX_CONFIG)
CONNECTOR_EXIT_LOCAL_SETUP = 78
_SHA256_REVISION_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class DastContractError(ValueError):
    """A local or provider payload does not match the v2 contract."""


class DastRunState(StrEnum):
    ACCEPTED = "accepted"
    SELECTING = "selecting"
    RUNNING = "running"
    STOP_REQUESTED = "stop_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"

    @property
    def terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.STOPPED}


class DastConnectorOutcomeState(StrEnum):
    TERMINAL = "terminal"
    CANCELLED_BEFORE_START = "cancelled_before_start"
    STOP_PENDING = "stop_pending"
    UNREACHABLE = "unreachable"


class DastTriggerType(StrEnum):
    GIT_BRANCH = "GIT_BRANCH"
    GIT_HASH = "GIT_HASH"


def _mapping(payload: object, name: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise DastContractError(f"{name} must be an object")
    return payload


def _exact_fields(payload: dict[str, Any], expected: set[str], name: str) -> None:
    if set(payload) != expected:
        raise DastContractError(f"{name} fields do not match the v2 contract")


def _required_string(value: object, name: str, *, max_length: int = 128) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise DastContractError(f"{name} is invalid")
    return value


def _required_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise DastContractError(f"{name} is invalid")
    return value


def _required_int(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise DastContractError(f"{name} is invalid")
    return value


def _contract_version(value: object) -> str:
    if value != CONTRACT_VERSION:
        raise DastContractError("unsupported DAST contract version")
    return CONTRACT_VERSION


def _run_state(value: object, name: str = "status") -> DastRunState:
    try:
        return DastRunState(value)
    except (TypeError, ValueError) as exc:
        raise DastContractError(f"{name} is invalid") from exc


def _valid_git_branch(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 255:
        return False
    if value.startswith(("-", ".", "/")) or value.endswith((".", "/", ".lock")):
        return False
    if ".." in value or "@{" in value or "//" in value:
        return False
    return not any(character.isspace() or ord(character) < 32 or character in "~^:?*[\\" for character in value)


@dataclass(frozen=True, slots=True)
class DastTrigger:
    repository_key: str
    type: DastTriggerType
    ref: str

    def __post_init__(self) -> None:
        if not _REPOSITORY_KEY_RE.fullmatch(self.repository_key):
            raise DastContractError("trigger.repository_key is invalid")
        try:
            trigger_type = DastTriggerType(self.type)
        except ValueError as exc:
            raise DastContractError("trigger.type is invalid") from exc
        object.__setattr__(self, "type", trigger_type)
        if trigger_type is DastTriggerType.GIT_HASH and not _COMMIT_RE.fullmatch(self.ref):
            raise DastContractError("trigger.ref must be a lowercase full git SHA")
        if trigger_type is DastTriggerType.GIT_BRANCH and not _valid_git_branch(self.ref):
            raise DastContractError("trigger.ref is not a safe branch name")

    @classmethod
    def from_wire(cls, payload: object) -> DastTrigger:
        data = _mapping(payload, "trigger")
        _exact_fields(data, {"repository_key", "type", "ref"}, "trigger")
        return cls(
            repository_key=_required_string(data["repository_key"], "trigger.repository_key"),
            type=_required_string(data["type"], "trigger.type"),
            ref=_required_string(data["ref"], "trigger.ref", max_length=255),
        )

    def to_wire(self) -> dict[str, str]:
        return {"repository_key": self.repository_key, "type": self.type.value, "ref": self.ref}


@dataclass(frozen=True, slots=True)
class DastStartCommand:
    idempotency_key: str
    correlation_id: str
    target_id: str
    capability_revision: str
    # None for a target whose scenario declares no repository-trigger requirement.
    trigger: DastTrigger | None
    parameters: dict[str, Any] | None = None
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _contract_version(self.contract_version)
        for value, name in (
            (self.idempotency_key, "idempotency_key"),
            (self.correlation_id, "correlation_id"),
            (self.target_id, "target_id"),
        ):
            if not _IDENTITY_RE.fullmatch(value):
                raise DastContractError(f"{name} is invalid")
        if not _SHA256_REVISION_RE.fullmatch(self.capability_revision):
            raise DastContractError("capability_revision is invalid")
        if self.parameters is not None and not isinstance(self.parameters, dict):
            raise DastContractError("parameters must be an object or null")
        object.__setattr__(self, "parameters", deepcopy(self.parameters))

    @classmethod
    def from_wire(cls, payload: object) -> DastStartCommand:
        data = _mapping(payload, "start request")
        expected = {
            "contract_version",
            "idempotency_key",
            "correlation_id",
            "target_id",
            "capability_revision",
            "trigger",
            "parameters",
        }
        if set(data) != expected and set(data) != expected - {"parameters"}:
            raise DastContractError("start request fields do not match the v2 contract")
        return cls(
            contract_version=_contract_version(data["contract_version"]),
            idempotency_key=_required_string(data["idempotency_key"], "idempotency_key"),
            correlation_id=_required_string(data["correlation_id"], "correlation_id"),
            target_id=_required_string(data["target_id"], "target_id"),
            capability_revision=_required_string(data["capability_revision"], "capability_revision"),
            trigger=DastTrigger.from_wire(data["trigger"]) if data.get("trigger") is not None else None,
            parameters=_mapping(data["parameters"], "parameters") if data.get("parameters") is not None else None,
        )

    def to_wire(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "idempotency_key": self.idempotency_key,
            "correlation_id": self.correlation_id,
            "target_id": self.target_id,
            "capability_revision": self.capability_revision,
            "trigger": self.trigger.to_wire() if self.trigger is not None else None,
            "parameters": deepcopy(self.parameters),
        }


@dataclass(frozen=True, slots=True)
class DastRecoveryState:
    correlation_id: str
    idempotency_key: str
    run_id: str | None = None
    log_cursor: int = 0
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _contract_version(self.contract_version)
        for value, name in (
            (self.correlation_id, "recovery.correlation_id"),
            (self.idempotency_key, "recovery.idempotency_key"),
        ):
            if not _IDENTITY_RE.fullmatch(value):
                raise DastContractError(f"{name} is invalid")
        if self.run_id is not None and not _IDENTITY_RE.fullmatch(self.run_id):
            raise DastContractError("recovery.run_id is invalid")
        _required_int(self.log_cursor, "recovery.log_cursor")

    @classmethod
    def initial(cls, command: DastStartCommand) -> DastRecoveryState:
        return cls(correlation_id=command.correlation_id, idempotency_key=command.idempotency_key)

    @classmethod
    def from_wire(cls, payload: object) -> DastRecoveryState:
        data = _mapping(payload, "recovery")
        _exact_fields(
            data,
            {"contract_version", "correlation_id", "idempotency_key", "run_id", "log_cursor"},
            "recovery",
        )
        return cls(
            contract_version=_contract_version(data["contract_version"]),
            correlation_id=_required_string(data["correlation_id"], "recovery.correlation_id"),
            idempotency_key=_required_string(data["idempotency_key"], "recovery.idempotency_key"),
            run_id=None if data["run_id"] is None else _required_string(data["run_id"], "recovery.run_id"),
            log_cursor=_required_int(data["log_cursor"], "recovery.log_cursor"),
        )

    @classmethod
    def from_file(cls, path: Path) -> DastRecoveryState:
        return cls.from_wire(json.loads(path.read_text(encoding="utf-8")))

    def for_run(self, run_id: str) -> DastRecoveryState:
        return DastRecoveryState(
            correlation_id=self.correlation_id,
            idempotency_key=self.idempotency_key,
            run_id=run_id,
            log_cursor=self.log_cursor,
        )

    def with_cursor(self, log_cursor: int) -> DastRecoveryState:
        return DastRecoveryState(
            correlation_id=self.correlation_id,
            idempotency_key=self.idempotency_key,
            run_id=self.run_id,
            log_cursor=log_cursor,
        )

    def to_wire(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "run_id": self.run_id,
            "log_cursor": self.log_cursor,
        }


@dataclass(frozen=True, slots=True)
class DastConnectorInput:
    gateway_url: str
    command: DastStartCommand
    recovery: DastRecoveryState
    deadline_at: str | None = None
    stop_requested: bool = False
    # Read the run's status once and collect a terminal result. No start, no stop.
    harvest_only: bool = False
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _contract_version(self.contract_version)
        if not self.gateway_url.startswith("https://") or self.gateway_url.endswith("/"):
            raise DastContractError("gateway_url must be a normalized HTTPS URL")
        if self.recovery.correlation_id != self.command.correlation_id:
            raise DastContractError("recovery correlation does not match start command")
        if self.recovery.idempotency_key != self.command.idempotency_key:
            raise DastContractError("recovery idempotency key does not match start command")
        if self.deadline_at is not None:
            _required_string(self.deadline_at, "deadline_at", max_length=64)
        _required_bool(self.stop_requested, "stop_requested")
        _required_bool(self.harvest_only, "harvest_only")

    @classmethod
    def from_wire(cls, payload: object) -> DastConnectorInput:
        data = _mapping(payload, "connector input")
        _exact_fields(
            data,
            {
                "contract_version",
                "gateway_url",
                "command",
                "recovery",
                "deadline_at",
                "stop_requested",
                "harvest_only",
            },
            "connector input",
        )
        return cls(
            contract_version=_contract_version(data["contract_version"]),
            gateway_url=_required_string(data["gateway_url"], "gateway_url", max_length=2048),
            command=DastStartCommand.from_wire(data["command"]),
            recovery=DastRecoveryState.from_wire(data["recovery"]),
            deadline_at=(
                None
                if data["deadline_at"] is None
                else _required_string(data["deadline_at"], "deadline_at", max_length=64)
            ),
            stop_requested=_required_bool(data["stop_requested"], "stop_requested"),
            harvest_only=_required_bool(data["harvest_only"], "harvest_only"),
        )

    def to_wire(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "gateway_url": self.gateway_url,
            "command": self.command.to_wire(),
            "recovery": self.recovery.to_wire(),
            "deadline_at": self.deadline_at,
            "stop_requested": self.stop_requested,
            "harvest_only": self.harvest_only,
        }


@dataclass(frozen=True, slots=True)
class DastConnectorOutcome:
    state: DastConnectorOutcomeState
    recovery: DastRecoveryState
    reason_code: str | None = None
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _contract_version(self.contract_version)
        object.__setattr__(self, "state", DastConnectorOutcomeState(self.state))
        if self.state is DastConnectorOutcomeState.TERMINAL and self.recovery.run_id is None:
            raise DastContractError("terminal connector outcome requires a provider run")
        if self.reason_code is not None:
            _required_string(self.reason_code, "connector outcome reason_code")

    @classmethod
    def from_wire(cls, payload: object) -> DastConnectorOutcome:
        data = _mapping(payload, "connector outcome")
        _exact_fields(data, {"contract_version", "state", "recovery", "reason_code"}, "connector outcome")
        try:
            state = DastConnectorOutcomeState(data["state"])
        except (TypeError, ValueError) as exc:
            raise DastContractError("connector outcome state is invalid") from exc
        return cls(
            contract_version=_contract_version(data["contract_version"]),
            state=state,
            recovery=DastRecoveryState.from_wire(data["recovery"]),
            reason_code=(
                None
                if data["reason_code"] is None
                else _required_string(data["reason_code"], "connector outcome reason_code")
            ),
        )

    @classmethod
    def from_file(cls, path: Path) -> DastConnectorOutcome:
        return cls.from_wire(json.loads(path.read_text(encoding="utf-8")))

    def to_wire(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "state": self.state.value,
            "recovery": self.recovery.to_wire(),
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class DastStartAccepted:
    run_id: str
    correlation_id: str
    status: DastRunState
    contract_version: str = CONTRACT_VERSION

    @classmethod
    def from_wire(cls, payload: object) -> DastStartAccepted:
        data = _mapping(payload, "start response")
        _exact_fields(data, {"contract_version", "run_id", "correlation_id", "status"}, "start response")
        status = _run_state(data["status"])
        if status is not DastRunState.ACCEPTED:
            raise DastContractError("start response status must be accepted")
        return cls(
            contract_version=_contract_version(data["contract_version"]),
            run_id=_required_string(data["run_id"], "run_id"),
            correlation_id=_required_string(data["correlation_id"], "correlation_id"),
            status=status,
        )


@dataclass(frozen=True, slots=True)
class DastRunStatus:
    run_id: str
    correlation_id: str
    status: DastRunState
    selection: dict[str, Any] | None
    error_code: str | None
    result_ready: bool
    contract_version: str = CONTRACT_VERSION

    @classmethod
    def from_wire(cls, payload: object) -> DastRunStatus:
        data = _mapping(payload, "run status")
        _exact_fields(
            data,
            {"contract_version", "run_id", "correlation_id", "status", "selection", "error_code", "result_ready"},
            "run status",
        )
        selection = data["selection"]
        if selection is not None:
            selection = _mapping(selection, "selection")
        error_code = data["error_code"]
        if error_code is not None:
            error_code = _required_string(error_code, "error_code")
        return cls(
            contract_version=_contract_version(data["contract_version"]),
            run_id=_required_string(data["run_id"], "run_id"),
            correlation_id=_required_string(data["correlation_id"], "correlation_id"),
            status=_run_state(data["status"]),
            selection=deepcopy(selection),
            error_code=error_code,
            result_ready=_required_bool(data["result_ready"], "result_ready"),
        )


@dataclass(frozen=True, slots=True)
class DastLogEvent:
    event_id: int
    level: str
    message: str
    timestamp: str | None

    MAX_MESSAGE_LENGTH: ClassVar[int] = 16 * 1024

    @classmethod
    def from_wire(cls, payload: object) -> DastLogEvent:
        data = _mapping(payload, "log event")
        _exact_fields(data, {"event_id", "level", "message", "timestamp"}, "log event")
        timestamp = data["timestamp"]
        if timestamp is not None:
            timestamp = _required_string(timestamp, "log timestamp", max_length=64)
        return cls(
            event_id=_required_int(data["event_id"], "event_id"),
            level=_required_string(data["level"], "log level", max_length=16),
            message=_required_string(data["message"], "log message", max_length=cls.MAX_MESSAGE_LENGTH),
            timestamp=timestamp,
        )


@dataclass(frozen=True, slots=True)
class DastLogPage:
    events: tuple[DastLogEvent, ...]
    next_cursor: int
    has_more: bool
    contract_version: str = CONTRACT_VERSION

    MAX_EVENTS: ClassVar[int] = 100

    @classmethod
    def from_wire(cls, payload: object, *, requested_cursor: int) -> DastLogPage:
        data = _mapping(payload, "log page")
        _exact_fields(data, {"contract_version", "events", "next_cursor", "has_more"}, "log page")
        raw_events = data["events"]
        if not isinstance(raw_events, list) or len(raw_events) > cls.MAX_EVENTS:
            raise DastContractError("log events are invalid")
        events = tuple(DastLogEvent.from_wire(event) for event in raw_events)
        event_ids = [event.event_id for event in events]
        if event_ids != sorted(set(event_ids)) or any(event_id < requested_cursor for event_id in event_ids):
            raise DastContractError("log event order is invalid")
        next_cursor = _required_int(data["next_cursor"], "next_cursor")
        if next_cursor < requested_cursor or (events and next_cursor <= events[-1].event_id):
            raise DastContractError("next_cursor is invalid")
        if data["has_more"] and not events:
            raise DastContractError("an empty log page cannot have more events")
        return cls(
            contract_version=_contract_version(data["contract_version"]),
            events=events,
            next_cursor=next_cursor,
            has_more=_required_bool(data["has_more"], "has_more"),
        )


@dataclass(frozen=True, slots=True)
class DastTerminalResult:
    run_id: str
    status: DastRunState
    selection: dict[str, Any]
    trigger_resolution: dict[str, Any] | None
    source_commits: dict[str, str]
    report: dict[str, Any]
    audit: dict[str, Any] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION

    @classmethod
    def from_wire(cls, payload: object) -> DastTerminalResult:
        data = _mapping(payload, "terminal result")
        _exact_fields(
            data,
            {
                "contract_version",
                "run_id",
                "status",
                "selection",
                "trigger_resolution",
                "dast_run_metadata",
                "report",
                "audit",
            },
            "terminal result",
        )
        status = _run_state(data["status"])
        if not status.terminal:
            raise DastContractError("terminal result has a non-terminal status")
        metadata = _mapping(data["dast_run_metadata"], "dast_run_metadata")
        _exact_fields(metadata, {"source_commits"}, "dast_run_metadata")
        source_commits = _mapping(metadata["source_commits"], "source_commits")
        for repository_key, commit in source_commits.items():
            if (
                not _REPOSITORY_KEY_RE.fullmatch(repository_key)
                or not isinstance(commit, str)
                or not _COMMIT_RE.fullmatch(commit)
            ):
                raise DastContractError("source_commits is invalid")
        trigger_resolution = data["trigger_resolution"]
        if trigger_resolution is not None:
            trigger_resolution = _mapping(trigger_resolution, "trigger_resolution")
        return cls(
            contract_version=_contract_version(data["contract_version"]),
            run_id=_required_string(data["run_id"], "run_id"),
            status=status,
            selection=deepcopy(_mapping(data["selection"], "selection")),
            trigger_resolution=deepcopy(trigger_resolution),
            source_commits=deepcopy(source_commits),
            report=deepcopy(_mapping(data["report"], "report")),
            audit=deepcopy(_mapping(data["audit"], "audit")),
        )

    @classmethod
    def from_file(cls, path: Path) -> DastTerminalResult:
        return cls.from_wire(json.loads(path.read_text(encoding="utf-8")))

    def to_wire(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "run_id": self.run_id,
            "status": self.status.value,
            "selection": deepcopy(self.selection),
            "trigger_resolution": deepcopy(self.trigger_resolution),
            "dast_run_metadata": {"source_commits": deepcopy(self.source_commits)},
            "report": deepcopy(self.report),
            "audit": deepcopy(self.audit),
        }


@dataclass(frozen=True, slots=True)
class DastErrorEnvelope:
    code: str
    message: str
    retryable: bool
    correlation_id: str | None

    @classmethod
    def from_wire(cls, payload: object) -> DastErrorEnvelope:
        data = _mapping(payload, "error response")
        _exact_fields(data, {"code", "message", "retryable", "correlation_id"}, "error response")
        correlation_id = data["correlation_id"]
        if correlation_id is not None:
            correlation_id = _required_string(correlation_id, "error correlation_id")
        return cls(
            code=_required_string(data["code"], "error code"),
            message=_required_string(data["message"], "error message", max_length=1024),
            retryable=_required_bool(data["retryable"], "retryable"),
            correlation_id=correlation_id,
        )
