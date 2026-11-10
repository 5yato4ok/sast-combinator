from __future__ import annotations

import json
import logging
import math
import os
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from pipeline import docker_utils
from pipeline.dast.contracts import (
    CONNECTOR_EXIT_LOCAL_SETUP,
    DastConnectorInput,
    DastConnectorOutcome,
    DastConnectorOutcomeState,
    DastRecoveryState,
    DastStartCommand,
    DastTerminalResult,
)
from pipeline.run_output import prepare_run_output_dir, write_json_atomically

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

#: How often this side looks at what the connector has written while its container runs. The
#: connector rewrites its recovery state once per gateway poll, so reading faster only costs
#: file reads and tells the caller nothing new.
_PROGRESS_POLL_SECONDS = 2.0

_CONNECTOR_INPUT = "/run/aist/input.json"
_CONNECTOR_OUTPUT = "/run/aist/output"
_CONNECTOR_TOKEN = "/run/secrets/dast-token"
_CONNECTOR_CA = "/run/secrets/dast-ca.pem"


@dataclass(frozen=True, slots=True)
class DastExecutionInput:
    pipeline_id: str
    gateway_url: str
    command: DastStartCommand
    workspace: Path
    output_dir: Path
    token_file: Path = field(repr=False)
    recovery: DastRecoveryState | None = None
    ca_file: Path | None = None
    vpn_container_name: str | None = None
    allowed_private_networks: tuple[str, ...] = ()
    stop_requested: bool = False
    #: Called with the connector's own recovery state while the run is still going: once the
    #: provider has accepted it, and again whenever the connector advances. A caller that keeps
    #: durable state uses this to learn the run's identity before the container exits, instead of
    #: waiting for the whole execution to return. Failures inside it never reach the run.
    on_progress: Callable[[DastRecoveryState], None] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.pipeline_id or not self.gateway_url.startswith("https://"):
            raise ValueError("DAST execution identity and HTTPS gateway URL are required")
        object.__setattr__(self, "workspace", Path(self.workspace).resolve())
        object.__setattr__(self, "output_dir", Path(self.output_dir).resolve())
        object.__setattr__(self, "token_file", Path(self.token_file).resolve())
        if self.ca_file is not None:
            object.__setattr__(self, "ca_file", Path(self.ca_file).resolve())


@dataclass(frozen=True, slots=True)
class DastExecutionTelemetry:
    logs_delivered: int
    max_log_lag_seconds: float | None

    @classmethod
    def empty(cls) -> DastExecutionTelemetry:
        return cls(logs_delivered=0, max_log_lag_seconds=None)

    @classmethod
    def from_file(cls, path: Path) -> DastExecutionTelemetry:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) != {
            "version",
            "logs_delivered",
            "max_log_lag_seconds",
        }:
            raise ValueError("DAST connector telemetry is invalid")
        logs_delivered = payload["logs_delivered"]
        lag = payload["max_log_lag_seconds"]
        if payload["version"] != 1 or not isinstance(logs_delivered, int) or isinstance(logs_delivered, bool):
            raise ValueError("DAST connector telemetry is invalid")
        if lag is not None and (
            not isinstance(lag, (int, float))
            or isinstance(lag, bool)
            or not math.isfinite(lag)
        ):
            raise ValueError("DAST connector telemetry is invalid")
        if logs_delivered < 0 or (lag is not None and lag < 0):
            raise ValueError("DAST connector telemetry is invalid")
        return cls(logs_delivered=logs_delivered, max_log_lag_seconds=float(lag) if lag is not None else None)


@dataclass(frozen=True, slots=True)
class DastExecutionResult:
    outcome: DastConnectorOutcome
    terminal_result: DastTerminalResult | None
    recovery: DastRecoveryState
    telemetry: DastExecutionTelemetry
    report_path: Path | None = None

    @classmethod
    def from_files(
        cls,
        result_path: Path,
        recovery_path: Path,
        outcome_path: Path,
        telemetry_path: Path,
    ) -> DastExecutionResult:
        outcome = DastConnectorOutcome.from_file(outcome_path)
        terminal_result = (
            DastTerminalResult.from_file(result_path)
            if outcome.state is DastConnectorOutcomeState.TERMINAL
            else None
        )
        return cls(
            outcome=outcome,
            terminal_result=terminal_result,
            recovery=DastRecoveryState.from_file(recovery_path),
            telemetry=DastExecutionTelemetry.from_file(telemetry_path),
        )


class DastExecutionIncomplete(RuntimeError):
    """The connector exited before it could persist a provider run checkpoint."""


class DastExecutionLocalFailure(RuntimeError):
    """The connector never reached the provider; another attempt would fail identically."""


# The connector is not a third-party tool wrapped in an image the way an analyzer is: it is this
# package's own code (`COPY pipeline/dast/`, `python -m pipeline.dast.connector`). So the package
# knows how to build it -- Dockerfile here, context at the package root -- instead of the analyzer
# catalog carrying build fields that only ever describe this one entry.
_CONNECTOR_DOCKERFILE_DIR = "Dockerfiles/dast_connector"
_CONNECTOR_BUILD_CONTEXT = "."
# Exactly what the runtime stage of that Dockerfile copies. The image tag names the protocol
# version, not a build, so a host that already has `:v2` would otherwise keep running the
# connector it built first -- and reject the input file this revision writes, because a field
# added to the v2 input contract does not exist in the packaged copy that parses it. Keep this
# list in step with the Dockerfile's COPY lines.
_CONNECTOR_SOURCE_PATHS = (
    "Dockerfiles/dast_connector/Dockerfile",
    "pipeline/__init__.py",
    "pipeline/docker_utils.py",
    "pipeline/run_output.py",
    "pipeline/dast",
)


class DastExecutor:
    """Run the DAST protocol connector through the shared container lifecycle and logger."""

    def __init__(self, *, connector_image: str, result_file: str):
        if not connector_image or not result_file or Path(result_file).name != result_file:
            raise ValueError("DAST connector image and result file are required")
        self._connector_image = connector_image
        self._result_file = result_file

    @contextmanager
    def _reporting_progress(self, recovery_path: Path, on_progress):
        """
        Report the connector's recovery state upward while its container is still running.

        The connector writes that state as soon as the provider accepts the run and again on every
        poll. Reading it here is what lets the caller learn the run's identity before the container
        exits; where the file lives and how often it is read stay inside this package.
        """
        if on_progress is None:
            yield
            return
        stop = threading.Event()
        watcher = threading.Thread(
            target=self._watch_recovery,
            args=(recovery_path, on_progress, stop),
            name=f"dast-progress-{recovery_path.parent.parent.name}",
            daemon=True,
        )
        watcher.start()
        try:
            yield
        finally:
            stop.set()
            watcher.join(timeout=_PROGRESS_POLL_SECONDS * 2)

    @staticmethod
    def _watch_recovery(recovery_path: Path, on_progress, stop: threading.Event) -> None:
        reported: tuple[str | None, int] | None = None
        while True:
            recovery = DastExecutor._read_recovery(recovery_path)
            if recovery is not None and (recovery.run_id, recovery.log_cursor) != reported:
                reported = (recovery.run_id, recovery.log_cursor)
                try:
                    on_progress(recovery)
                except Exception:
                    # Reporting is observation. A caller that cannot record what it was told must
                    # not take the run down with it.
                    logger.exception("DAST progress report failed for %s", recovery_path)
            if stop.wait(_PROGRESS_POLL_SECONDS):
                return

    @staticmethod
    def _read_recovery(recovery_path: Path) -> DastRecoveryState | None:
        """The connector's recovery state, or nothing if it has not written a readable one yet."""
        try:
            if not recovery_path.is_file():
                return None
            return DastRecoveryState.from_file(recovery_path)
        except Exception:
            # The file is replaced atomically, so this is a malformed or half-provisioned run
            # rather than a torn read. Either way it is not something to report.
            return None

    def execute(self, execution: DastExecutionInput) -> DastExecutionResult:
        self._validate_secret_file(execution.token_file)
        if execution.ca_file is not None and not execution.ca_file.is_file():
            raise ValueError("DAST CA file does not exist")

        execution.workspace.mkdir(parents=True, exist_ok=True)
        input_path = execution.workspace / "input.json"
        output_dir = execution.workspace / "output"
        output_dir.mkdir(mode=0o700, exist_ok=True)
        connector_input = DastConnectorInput(
            gateway_url=execution.gateway_url.rstrip("/"),
            command=execution.command,
            recovery=execution.recovery or DastRecoveryState.initial(execution.command),
            stop_requested=execution.stop_requested,
        )
        input_path.write_text(
            json.dumps(connector_input.to_wire(), sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        input_path.chmod(0o600)

        volumes = {
            str(input_path): f"{_CONNECTOR_INPUT}:ro",
            str(output_dir): _CONNECTOR_OUTPUT,
            str(execution.token_file): f"{_CONNECTOR_TOKEN}:ro",
        }
        args = ["--input", _CONNECTOR_INPUT, "--output", _CONNECTOR_OUTPUT, "--token-file", _CONNECTOR_TOKEN]
        if execution.ca_file is not None:
            volumes[str(execution.ca_file)] = f"{_CONNECTOR_CA}:ro"
            args.extend(["--ca-file", _CONNECTOR_CA])
        if execution.vpn_container_name:
            args.append("--trusted-vpn")

        # The image has to exist before it can be asked who it runs as, and the answer decides
        # how the handoff is aligned; run_pipeline_container's own ensure_image then finds it.
        docker_utils.ensure_image(
            self._connector_image,
            _CONNECTOR_DOCKERFILE_DIR,
            build_context=_CONNECTOR_BUILD_CONTEXT,
            source_digest=docker_utils.build_source_digest(_CONNECTOR_SOURCE_PATHS),
        )
        mounted = [input_path, output_dir, execution.token_file]
        if execution.ca_file is not None:
            mounted.append(execution.ca_file)
        user = self._align_handoff_identity(mounted)

        try:
            with self._reporting_progress(output_dir / "recovery.json", execution.on_progress):
                docker_utils.run_pipeline_container(
                    image=self._connector_image,
                    dockerfile_dir=_CONNECTOR_DOCKERFILE_DIR,
                    build_context=_CONNECTOR_BUILD_CONTEXT,
                    pipeline_id=execution.pipeline_id,
                    volumes=volumes,
                    env={"AIST_DAST_ALLOWED_PRIVATE_NETWORKS": ",".join(execution.allowed_private_networks)},
                    args=args,
                    network=f"container:{execution.vpn_container_name}" if execution.vpn_container_name else None,
                    user=user,
                )
        except subprocess.CalledProcessError as exc:
            self._cleanup_connector_container(execution.pipeline_id)
            if exc.returncode == CONNECTOR_EXIT_LOCAL_SETUP:
                detail = "DAST connector could not start on this host"
                raise DastExecutionLocalFailure(detail) from exc
            recovery_path = output_dir / "recovery.json"
            if not recovery_path.is_file():
                raise DastExecutionIncomplete("DAST connector failed before provider acceptance") from exc
            recovery = DastRecoveryState.from_file(recovery_path)
            return DastExecutionResult(
                outcome=DastConnectorOutcome(
                    state=DastConnectorOutcomeState.UNREACHABLE,
                    recovery=recovery,
                ),
                terminal_result=None,
                recovery=recovery,
                telemetry=DastExecutionTelemetry.empty(),
            )
        except BaseException:
            self._cleanup_connector_container(execution.pipeline_id)
            raise

        result_path = output_dir / "result.json"
        recovery_path = output_dir / "recovery.json"
        outcome_path = output_dir / "outcome.json"
        telemetry_path = output_dir / "telemetry.json"
        if not recovery_path.is_file():
            raise ValueError("DAST connector did not produce recovery.json")
        if not outcome_path.is_file():
            raise ValueError("DAST connector did not produce outcome.json")
        if not telemetry_path.is_file():
            raise ValueError("DAST connector did not produce telemetry.json")
        result = DastExecutionResult.from_files(result_path, recovery_path, outcome_path, telemetry_path)
        if result.outcome.recovery != result.recovery:
            raise ValueError("DAST connector outcome and recovery state do not match")
        if result.outcome.state is DastConnectorOutcomeState.TERMINAL and not result_path.is_file():
            raise ValueError("terminal DAST connector did not produce result.json")
        if result.outcome.state is not DastConnectorOutcomeState.TERMINAL and result_path.exists():
            raise ValueError("non-terminal DAST connector produced an unexpected result.json")
        if result.terminal_result is not None:
            report_path = write_json_atomically(
                prepare_run_output_dir(execution.output_dir),
                self._result_file,
                result.terminal_result.report,
            )
            result = DastExecutionResult(
                outcome=result.outcome,
                terminal_result=result.terminal_result,
                recovery=result.recovery,
                telemetry=result.telemetry,
                report_path=report_path,
            )
        return result

    def _cleanup_connector_container(self, pipeline_id: str) -> None:
        """Remove the connector container this executor started, and nothing else.

        `docker run --rm` covers ordinary exits; this catches what an interrupted `docker run`
        leaves behind, whose name would block the next attempt. Scoped to one exact name because a
        pipeline-id match also covers the VPN sidecar, which belongs to the caller's context.
        """
        docker_utils.cleanup_container(
            docker_utils.construct_container_name(self._connector_image, pipeline_id),
        )

    def _align_handoff_identity(self, mounted: list[Path]) -> str | None:
        """Give the handoff files and the container one identity, and return any ``--user``.

        The token must stay unreadable to anyone but its owner, so relaxing the mode is not an
        option: the two sides have to agree on who that owner is. When this process can hand the
        files over it does, and the image keeps the unprivileged user it declares; otherwise the
        container runs as this process instead.
        """
        image_user = docker_utils.image_runtime_user(self._connector_image)
        if image_user is not None and os.geteuid() == 0:
            uid, gid = image_user
            for path in mounted:
                os.chown(path, uid, gid)
            return None
        return f"{os.geteuid()}:{os.getegid()}"

    @staticmethod
    def _validate_secret_file(path: Path) -> None:
        if not path.is_file():
            raise ValueError("DAST token file does not exist")
        if os.stat(path).st_mode & 0o077:
            raise ValueError("DAST token file must not be accessible by group or other users")
