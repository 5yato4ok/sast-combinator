"""Single-owner Python connector for the DAST integration gateway v2 run protocol."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx

from pipeline.dast.contracts import (
    CONNECTOR_EXIT_LOCAL_SETUP,
    DastConnectorInput,
    DastConnectorOutcome,
    DastConnectorOutcomeState,
    DastContractError,
    DastErrorEnvelope,
    DastLogPage,
    DastRecoveryState,
    DastRunStatus,
    DastStartAccepted,
    DastTerminalResult,
)
from pipeline.dast.endpoint_policy import DastEndpointPolicy, DastEndpointPolicyError


class DastGatewayError(RuntimeError):
    def __init__(self, error: DastErrorEnvelope, *, status_code: int):
        self.error = error
        self.status_code = status_code
        super().__init__(f"DAST gateway rejected the request: {error.code}")


class DastConnectorError(RuntimeError):
    """The remote protocol could not be completed safely."""


class DastGatewayClient:
    START_PATH: ClassVar[str] = "/integrations/v2/runs"
    MAX_ATTEMPTS: ClassVar[int] = 3
    MAX_CONTROL_RESPONSE_BYTES: ClassVar[int] = 1024 * 1024
    MAX_RESULT_BYTES: ClassVar[int] = 16 * 1024 * 1024
    RETRYABLE_STATUS_CODES: ClassVar[frozenset[int]] = frozenset({429, 502, 503, 504})

    def __init__(
        self,
        *,
        gateway_url: str,
        token: str,
        ca_file: Path | None = None,
        trusted_vpn: bool = False,
        resolver: Callable[[str, int], Iterable[str]] | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if gateway_url.endswith("/"):
            raise DastConnectorError("gateway_url must be a normalized HTTPS URL")
        if not token:
            raise DastConnectorError("DAST token is empty")
        try:
            DastEndpointPolicy(trusted_vpn=trusted_vpn, resolver=resolver).validate(gateway_url)
        except DastEndpointPolicyError as exc:
            raise DastConnectorError(str(exc)) from exc
        self._sleep = sleep
        self._owns_client = client is None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if client is None:
            client = httpx.Client(
                base_url=gateway_url,
                headers=headers,
                timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
                limits=httpx.Limits(max_connections=4, max_keepalive_connections=2, keepalive_expiry=15.0),
                verify=str(ca_file) if ca_file else True,
                follow_redirects=False,
                trust_env=False,
            )
        else:
            client.headers.update(headers)
        self._client = client

    def __enter__(self) -> DastGatewayClient:
        return self

    def __exit__(self, *_exc_info) -> None:
        if self._owns_client:
            self._client.close()

    def start(self, command) -> DastStartAccepted:
        payload = self._request_json(
            "POST",
            self.START_PATH,
            expected_status=202,
            json_body=command.to_wire(),
            retry_allowed=True,
            response_limit=self.MAX_CONTROL_RESPONSE_BYTES,
        )
        accepted = DastStartAccepted.from_wire(payload)
        if accepted.correlation_id != command.correlation_id:
            raise DastConnectorError("start response correlation does not match the command")
        return accepted

    def status(self, run_id: str) -> DastRunStatus:
        payload = self._request_json(
            "GET",
            f"{self.START_PATH}/{run_id}",
            expected_status=200,
            retry_allowed=True,
            response_limit=self.MAX_CONTROL_RESPONSE_BYTES,
        )
        status = DastRunStatus.from_wire(payload)
        if status.run_id != run_id:
            raise DastConnectorError("status response run identity does not match")
        return status

    def logs(self, run_id: str, *, cursor: int) -> DastLogPage:
        payload = self._request_json(
            "GET",
            f"{self.START_PATH}/{run_id}/logs",
            expected_status=200,
            params={"cursor": cursor, "limit": DastLogPage.MAX_EVENTS},
            retry_allowed=True,
            response_limit=self.MAX_CONTROL_RESPONSE_BYTES,
        )
        return DastLogPage.from_wire(payload, requested_cursor=cursor)

    def result(self, run_id: str) -> DastTerminalResult:
        payload = self._request_json(
            "GET",
            f"{self.START_PATH}/{run_id}/results",
            expected_status=200,
            retry_allowed=True,
            response_limit=self.MAX_RESULT_BYTES,
        )
        result = DastTerminalResult.from_wire(payload)
        if result.run_id != run_id:
            raise DastConnectorError("result response run identity does not match")
        return result

    def stop(self, run_id: str) -> DastRunStatus:
        payload = self._request_json(
            "POST",
            f"{self.START_PATH}/{run_id}/stop",
            expected_status=200,
            retry_allowed=True,
            response_limit=self.MAX_CONTROL_RESPONSE_BYTES,
        )
        if not isinstance(payload, dict) or "stop_requested" not in payload:
            raise DastContractError("stop response fields do not match the v2 contract")
        stop_requested = payload.pop("stop_requested")
        if not isinstance(stop_requested, bool):
            raise DastContractError("stop_requested is invalid")
        status = DastRunStatus.from_wire(payload)
        if status.run_id != run_id:
            raise DastConnectorError("stop response run identity does not match")
        return status

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        expected_status: int,
        retry_allowed: bool,
        response_limit: int,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                with self._client.stream(method, path, json=json_body, params=params) as response:
                    if 300 <= response.status_code < 400:
                        raise DastConnectorError("DAST gateway redirects are forbidden")
                    payload = self._read_bounded_json(response, limit=response_limit)
            except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException) as exc:
                if retry_allowed and attempt < self.MAX_ATTEMPTS:
                    self._bounded_backoff(attempt)
                    continue
                raise DastConnectorError("DAST gateway is unreachable") from exc

            if response.status_code == expected_status:
                return payload

            try:
                error = DastErrorEnvelope.from_wire(payload)
            except DastContractError as exc:
                raise DastConnectorError("DAST gateway returned an invalid error envelope") from exc
            retryable = error.retryable or response.status_code in self.RETRYABLE_STATUS_CODES
            if retry_allowed and retryable and attempt < self.MAX_ATTEMPTS:
                self._bounded_backoff(attempt)
                continue
            raise DastGatewayError(error, status_code=response.status_code)
        raise AssertionError("bounded retry loop exhausted without returning")

    def _bounded_backoff(self, attempt: int) -> None:
        self._sleep(min(0.25 * (2 ** (attempt - 1)), 1.0))

    @staticmethod
    def _read_bounded_json(response: httpx.Response, *, limit: int) -> Any:
        content_type = response.headers.get("Content-Type", "").partition(";")[0].strip().lower()
        if content_type != "application/json":
            raise DastConnectorError("DAST gateway response is not JSON")
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > limit:
                    raise DastConnectorError("DAST gateway response exceeds its size limit")
            except ValueError as exc:
                raise DastConnectorError("DAST gateway Content-Length is invalid") from exc
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > limit:
                raise DastConnectorError("DAST gateway response exceeds its size limit")
        try:
            return json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DastConnectorError("DAST gateway response contains invalid JSON") from exc


class DastConnector:
    def __init__(
        self,
        *,
        gateway: DastGatewayClient,
        output_dir: Path,
        poll_interval: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] | None = None,
    ):
        self._gateway = gateway
        self._output_dir = output_dir
        self._poll_interval = poll_interval
        self._sleep = sleep
        self._now = now or (lambda: datetime.now(UTC))
        self._logs_delivered = 0
        self._max_log_lag_seconds: float | None = None

    def run(self, connector_input: DastConnectorInput) -> DastTerminalResult | None:
        recovery = connector_input.recovery
        correlation_id = connector_input.command.correlation_id
        if connector_input.harvest_only:
            return self._harvest(recovery, correlation_id=correlation_id)
        deadline_reached = self._deadline_reached(connector_input.deadline_at)
        if connector_input.stop_requested or deadline_reached:
            reason_code = "EXECUTION_TIMEOUT" if deadline_reached else "CANCEL_REQUESTED"
            if recovery.run_id is None:
                self._write_recovery(recovery)
                self._write_outcome(
                    DastConnectorOutcomeState.CANCELLED_BEFORE_START,
                    recovery,
                    reason_code=reason_code,
                )
                return None
            return self._stop_unless_already_terminal(
                recovery,
                correlation_id=correlation_id,
                reason_code=reason_code,
            )
        if recovery.run_id is None:
            accepted = self._gateway.start(connector_input.command)
            recovery = recovery.for_run(accepted.run_id)
            self._write_recovery(recovery)

        try:
            while True:
                if self._deadline_reached(connector_input.deadline_at):
                    return self._stop_unless_already_terminal(
                        recovery,
                        correlation_id=correlation_id,
                        reason_code="EXECUTION_TIMEOUT",
                    )
                status = self._gateway.status(recovery.run_id)
                if status.correlation_id != correlation_id:
                    raise DastConnectorError("status response correlation does not match the command")
                recovery = self._drain_logs(recovery)
                self._write_recovery(recovery)
                if status.status.terminal:
                    return self._collect_terminal(
                        status,
                        recovery,
                        reason_code=status.error_code,
                        source="status",
                    )
                self._sleep(self._poll_interval)
        except (KeyboardInterrupt, SystemExit):
            self._gateway.stop(recovery.run_id)
            self._write_outcome(
                DastConnectorOutcomeState.STOP_PENDING,
                recovery,
                reason_code="CANCEL_REQUESTED",
            )
            return None

    def _harvest(
        self,
        recovery: DastRecoveryState,
        *,
        correlation_id: str,
    ) -> DastTerminalResult | None:
        """Read the run's status once, collecting a terminal result. Neither starts nor stops a run.

        Used when the caller has already decided to end the pipeline and only needs to know whether
        a result exists.
        """
        if recovery.run_id is None:
            self._write_recovery(recovery)
            self._write_outcome(
                DastConnectorOutcomeState.CANCELLED_BEFORE_START,
                recovery,
                reason_code="EXECUTION_TIMEOUT",
            )
            return None
        status = self._gateway.status(recovery.run_id)
        if status.correlation_id != correlation_id:
            raise DastConnectorError("status response correlation does not match the command")
        recovery = self._drain_logs(recovery)
        self._write_recovery(recovery)
        if status.status.terminal:
            return self._collect_terminal(
                status,
                recovery,
                reason_code=status.error_code,
                source="status",
            )
        self._write_outcome(
            DastConnectorOutcomeState.STOP_PENDING,
            recovery,
            reason_code="EXECUTION_TIMEOUT",
        )
        return None

    def _stop_unless_already_terminal(
        self,
        recovery: DastRecoveryState,
        *,
        correlation_id: str,
        reason_code: str,
    ) -> DastTerminalResult | None:
        """Collect the result if the run already finished; otherwise request a stop.

        Stopping first would leave a finished run's result unfetched.
        """
        status = self._gateway.status(recovery.run_id)
        if status.correlation_id != correlation_id:
            raise DastConnectorError("status response correlation does not match the command")
        if status.status.terminal:
            recovery = self._drain_logs(recovery)
            self._write_recovery(recovery)
            return self._collect_terminal(
                status,
                recovery,
                reason_code=status.error_code or reason_code,
                source="status",
            )
        return self._request_stop(recovery, reason_code=reason_code)

    def _request_stop(
        self,
        recovery: DastRecoveryState,
        *,
        reason_code: str,
    ) -> DastTerminalResult | None:
        status = self._gateway.stop(recovery.run_id)
        recovery = self._drain_logs(recovery)
        self._write_recovery(recovery)
        if status.status.terminal:
            return self._collect_terminal(
                status,
                recovery,
                reason_code=status.error_code or reason_code,
                source="stop status",
            )
        self._write_outcome(
            DastConnectorOutcomeState.STOP_PENDING,
            recovery,
            reason_code=reason_code,
        )
        return None

    def _collect_terminal(
        self,
        status: DastRunStatus,
        recovery: DastRecoveryState,
        *,
        reason_code: str | None,
        source: str,
    ) -> DastTerminalResult:
        """Fetch and persist the result of a run the provider reports as terminal."""
        if not status.result_ready:
            raise DastConnectorError(f"terminal DAST {source} has no result")
        result = self._gateway.result(recovery.run_id)
        if result.status is not status.status:
            raise DastConnectorError(f"terminal result status does not match {source}")
        self._write_json("result.json", result.to_wire())
        self._write_outcome(
            DastConnectorOutcomeState.TERMINAL,
            recovery,
            reason_code=reason_code,
        )
        return result

    def _deadline_reached(self, deadline_at: str | None) -> bool:
        if deadline_at is None:
            return False
        try:
            deadline = datetime.fromisoformat(deadline_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DastConnectorError("DAST execution deadline is invalid") from exc
        if deadline.tzinfo is None:
            raise DastConnectorError("DAST execution deadline must include a timezone")
        return self._now() >= deadline

    def _drain_logs(self, recovery: DastRecoveryState) -> DastRecoveryState:
        while True:
            page = self._gateway.logs(recovery.run_id, cursor=recovery.log_cursor)
            for event in page.events:
                self._logs_delivered += 1
                if event.timestamp:
                    try:
                        timestamp = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
                    except ValueError:
                        timestamp = None
                    if timestamp is not None and timestamp.tzinfo is not None:
                        lag = max(0.0, (self._now() - timestamp).total_seconds())
                        self._max_log_lag_seconds = max(self._max_log_lag_seconds or 0.0, lag)
                level = event.level.upper()
                if level not in {"DEBUG", "INFO", "WARNING", "WARN", "ERROR", "ERR", "CRITICAL", "CRIT"}:
                    level = "INFO"
                message = event.message.replace("\r", "\\r").replace("\n", "\\n")
                print(f"[{level}] {message}", flush=True)
            recovery = recovery.with_cursor(page.next_cursor)
            self._write_recovery(recovery)
            if not page.has_more:
                return recovery

    def _write_recovery(self, recovery: DastRecoveryState) -> None:
        self._write_json("recovery.json", recovery.to_wire())

    def _write_outcome(
        self,
        state: DastConnectorOutcomeState,
        recovery: DastRecoveryState,
        *,
        reason_code: str | None = None,
    ) -> None:
        self._write_json(
            "telemetry.json",
            {
                "version": 1,
                "logs_delivered": self._logs_delivered,
                "max_log_lag_seconds": self._max_log_lag_seconds,
            },
        )
        self._write_json(
            "outcome.json",
            DastConnectorOutcome(state=state, recovery=recovery, reason_code=reason_code).to_wire(),
        )

    def _write_json(self, filename: str, payload: dict[str, Any]) -> None:
        self._output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary_path = self._output_dir / f".{filename}.tmp"
        final_path = self._output_dir / filename
        temporary_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        temporary_path.chmod(0o600)
        temporary_path.replace(final_path)


def _load_input(path: Path) -> DastConnectorInput:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DastConnectorError("connector input is unreadable") from exc
    return DastConnectorInput.from_wire(payload)


def _ensure_output_writable(path: Path) -> None:
    """Fail here rather than after the provider has already accepted a run.

    The output directory is how a run survives this process: without it the connector reaches the
    provider, starts a scan, and then cannot write the checkpoint that would let anyone resume it.
    """
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        probe = path / ".writable"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise DastConnectorError("connector output directory is not writable") from exc


def _load_token(path: Path) -> str:
    try:
        if os.stat(path).st_mode & 0o077:
            raise DastConnectorError("DAST token file permissions are too broad")
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise DastConnectorError("DAST token file is unreadable") from exc
    if not token:
        raise DastConnectorError("DAST token is empty")
    return token


def _interrupt(_signum, _frame) -> None:
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one DAST gateway v2 execution")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--ca-file", type=Path)
    parser.add_argument("--trusted-vpn", action="store_true")
    args = parser.parse_args(argv)

    signal.signal(signal.SIGTERM, _interrupt)
    # The handoff files are local state: they fail the same way on every attempt, so they exit
    # with a code that tells the caller not to retry. Everything after this -- including name
    # resolution of the gateway -- can differ on the next attempt and stays retryable.
    try:
        connector_input = _load_input(args.input)
        token = _load_token(args.token_file)
        _ensure_output_writable(args.output)
    except (DastContractError, DastConnectorError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr, flush=True)
        return CONNECTOR_EXIT_LOCAL_SETUP
    try:
        with DastGatewayClient(
            gateway_url=connector_input.gateway_url,
            token=token,
            ca_file=args.ca_file,
            trusted_vpn=args.trusted_vpn,
        ) as gateway:
            DastConnector(gateway=gateway, output_dir=args.output).run(connector_input)
    except (DastContractError, DastConnectorError, DastGatewayError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        print("[WARNING] DAST connector interrupted after requesting provider stop", file=sys.stderr, flush=True)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
