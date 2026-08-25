import gc
import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
import pipeline.dast.connector as connector_module
from pipeline.dast.connector import (
    DastConnector,
    DastConnectorError,
    DastGatewayClient,
    DastGatewayError,
    main,
)
from pipeline.dast.contracts import (
    CONNECTOR_EXIT_LOCAL_SETUP,
    DastConnectorInput,
    DastRecoveryState,
    DastStartCommand,
)
from pipeline.dast.resilience import HANDSHAKE, IMPATIENT, IN_FLIGHT, WATCH

CAPABILITY_REVISION = f"sha256:{'a' * 64}"


def _command():
    return DastStartCommand.from_wire(
        {
            "contract_version": "2.0",
            "idempotency_key": "launch-123",
            "correlation_id": "pipeline-123",
            "target_id": "cloud-backend",
            "capability_revision": CAPABILITY_REVISION,
            "trigger": {"repository_key": "backend", "type": "GIT_HASH", "ref": "b" * 40},
            "parameters": {"depth": "light"},
        }
    )


def _connector_input(*, recovery=None):
    command = _command()
    return DastConnectorInput(
        gateway_url="https://dast.internal",
        command=command,
        recovery=recovery or DastRecoveryState.initial(command),
    )


def _accepted():
    return {
        "contract_version": "2.0",
        "run_id": "run-123",
        "correlation_id": "pipeline-123",
        "status": "accepted",
    }


def _status(status, *, result_ready=False, error_code=None):
    return {
        "contract_version": "2.0",
        "run_id": "run-123",
        "correlation_id": "pipeline-123",
        "status": status,
        "selection": {"stand_id": "qa", "relation": "exact", "distance": 0},
        "error_code": error_code,
        "result_ready": result_ready,
    }


def _logs(cursor, *, message=None, timestamp=None):
    events = []
    next_cursor = cursor
    if message is not None:
        events = [{"event_id": cursor, "level": "info", "message": message, "timestamp": timestamp}]
        next_cursor = cursor + 1
    return {"contract_version": "2.0", "events": events, "next_cursor": next_cursor, "has_more": False}


def _result(**overrides):
    payload = {
        "contract_version": "2.0",
        "run_id": "run-123",
        "status": "succeeded",
        "selection": {"stand_id": "qa", "relation": "exact", "distance": 0},
        "trigger_resolution": None,
        "dast_run_metadata": {"source_commits": {"backend": "b" * 40}},
        "report": {"findings": []},
        "audit": {"provider": "dast"},
    }
    payload.update(overrides)
    return payload


def _outcome(state, recovery, *, reason_code=None):
    return {
        "contract_version": "2.0",
        "state": state,
        "recovery": recovery.to_wire(),
        "reason_code": reason_code,
    }


def _response(status_code, payload):
    return httpx.Response(status_code, json=payload, headers={"Content-Type": "application/json"})


class _Clock:
    """A clock that moves only when the client sleeps: real budgets, no real waiting."""

    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


def _gateway(handler, *, clock=None, plan=WATCH, may_retry=None, on_retry=None):
    client = httpx.Client(base_url="https://dast.internal", transport=httpx.MockTransport(handler))
    clock = clock if clock is not None else _Clock()
    return DastGatewayClient(
        gateway_url="https://dast.internal",
        token="public.secret",
        client=client,
        resolver=lambda _hostname, _port: ("8.8.8.8",),
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        plan=plan,
        may_retry=may_retry,
        on_retry=on_retry,
    )


def test_connector_owns_start_poll_log_and_clean_result_protocol(tmp_path, capsys):
    status_calls = 0
    requests = []

    def handler(request):
        nonlocal status_calls
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer public.secret"
        if request.method == "POST":
            assert json.loads(request.content) == _command().to_wire()
            return _response(202, _accepted())
        if request.url.path.endswith("/logs"):
            cursor = int(request.url.params["cursor"])
            return _response(
                200,
                _logs(
                    cursor,
                    message="scan\nstarted" if cursor == 0 else None,
                    timestamp="2026-07-26T09:59:55Z" if cursor == 0 else None,
                ),
            )
        if request.url.path.endswith("/results"):
            return _response(200, _result())
        status_calls += 1
        return _response(200, _status("running") if status_calls == 1 else _status("succeeded", result_ready=True))

    output_dir = tmp_path / "output"
    result = DastConnector(
        gateway=_gateway(handler),
        output_dir=output_dir,
        poll_interval=0,
        sleep=lambda _seconds: None,
        now=lambda: datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
    ).run(_connector_input())

    assert result.status == "succeeded"
    assert result.source_commits == {"backend": "b" * 40}
    assert json.loads((output_dir / "result.json").read_text(encoding="utf-8")) == _result()
    assert json.loads((output_dir / "recovery.json").read_text(encoding="utf-8"))["log_cursor"] == 1
    assert json.loads((output_dir / "outcome.json").read_text(encoding="utf-8"))["state"] == "terminal"
    assert json.loads((output_dir / "telemetry.json").read_text(encoding="utf-8")) == {
        "logs_delivered": 1,
        "max_log_lag_seconds": 5.0,
        "version": 1,
    }
    assert capsys.readouterr().out == "[INFO] scan\\nstarted\n"
    assert [request.url.path for request in requests] == [
        "/integrations/v2/runs",
        "/integrations/v2/runs/run-123",
        "/integrations/v2/runs/run-123/logs",
        "/integrations/v2/runs/run-123",
        "/integrations/v2/runs/run-123/logs",
        "/integrations/v2/runs/run-123/results",
    ]


def test_terminal_provider_reason_is_preserved_only_as_a_machine_code(tmp_path):
    def handler(request):
        if request.method == "POST":
            return _response(202, _accepted())
        if request.url.path.endswith("/logs"):
            return _response(200, _logs(0))
        if request.url.path.endswith("/results"):
            return _response(200, _result(status="failed", report={"findings": []}))
        return _response(
            200,
            _status("failed", result_ready=True, error_code="NO_ELIGIBLE_STAND"),
        )

    DastConnector(
        gateway=_gateway(handler),
        output_dir=tmp_path,
        poll_interval=0,
        sleep=lambda _seconds: None,
    ).run(_connector_input())

    outcome = json.loads((tmp_path / "outcome.json").read_text(encoding="utf-8"))
    assert outcome["state"] == "terminal"
    assert outcome["reason_code"] == "NO_ELIGIBLE_STAND"


def test_idempotency_retry_and_explicit_recovery_do_not_create_second_provider_run(tmp_path):
    start_attempts = []
    logical_provider_runs = set()
    simulate_lost_response = True

    def handler(request):
        nonlocal simulate_lost_response
        if request.method == "POST":
            body = json.loads(request.content)
            start_attempts.append(body)
            logical_provider_runs.add(body["idempotency_key"])
            if simulate_lost_response:
                simulate_lost_response = False
                raise httpx.ReadTimeout("accepted response was lost", request=request)
            return _response(202, _accepted())
        if request.url.path.endswith("/logs"):
            return _response(200, _logs(int(request.url.params["cursor"])))
        if request.url.path.endswith("/results"):
            return _response(200, _result())
        return _response(200, _status("succeeded", result_ready=True))

    connector = DastConnector(gateway=_gateway(handler), output_dir=tmp_path / "first", sleep=lambda _: None)
    connector.run(_connector_input())
    recovery = DastRecoveryState.from_wire(
        json.loads((tmp_path / "first" / "recovery.json").read_text(encoding="utf-8")),
    )
    DastConnector(gateway=_gateway(handler), output_dir=tmp_path / "resume", sleep=lambda _: None).run(
        _connector_input(recovery=recovery),
    )

    assert len(start_attempts) == 2
    assert start_attempts[0] == start_attempts[1]
    assert logical_provider_runs == {"launch-123"}


def test_recovery_cursor_preserves_log_order_without_replaying_delivered_events(tmp_path, capsys):
    first_status_calls = 0

    def first_handler(request):
        nonlocal first_status_calls
        if request.method == "POST":
            return _response(202, _accepted())
        if request.url.path.endswith("/logs"):
            cursor = int(request.url.params["cursor"])
            if cursor == 0:
                return _response(
                    200,
                    {
                        "contract_version": "2.0",
                        "events": [{"event_id": 0, "level": "info", "message": "zero", "timestamp": None}],
                        "next_cursor": 1,
                        "has_more": True,
                    },
                )
            return _response(200, _logs(cursor, message="one"))
        first_status_calls += 1
        if first_status_calls == 1:
            return _response(200, _status("running"))
        raise httpx.ConnectError("provider disconnected", request=request)

    first_output = tmp_path / "first"
    with pytest.raises(DastConnectorError, match="unreachable"):
        DastConnector(
            gateway=_gateway(first_handler),
            output_dir=first_output,
            poll_interval=0,
            sleep=lambda _seconds: None,
        ).run(_connector_input())

    recovery = DastRecoveryState.from_wire(
        json.loads((first_output / "recovery.json").read_text(encoding="utf-8")),
    )
    assert recovery.log_cursor == 2
    resumed_requests = []

    def resumed_handler(request):
        resumed_requests.append(request)
        if request.url.path.endswith("/logs"):
            assert int(request.url.params["cursor"]) == 2
            return _response(200, _logs(2, message="two"))
        if request.url.path.endswith("/results"):
            return _response(200, _result())
        assert request.method == "GET"
        return _response(200, _status("succeeded", result_ready=True))

    DastConnector(
        gateway=_gateway(resumed_handler),
        output_dir=tmp_path / "resumed",
        sleep=lambda _seconds: None,
    ).run(_connector_input(recovery=recovery))

    assert capsys.readouterr().out.splitlines() == ["[INFO] zero", "[INFO] one", "[INFO] two"]
    assert all(request.method != "POST" for request in resumed_requests)


def test_large_cursor_log_stream_keeps_memory_and_recovery_writes_bounded(monkeypatch, tmp_path):
    page_count = 250
    page_size = 100

    class TrackedEvent:
        live = 0
        maximum_live = 0

        def __init__(self, event_id):
            self.event_id = event_id
            self.level = "info"
            self.message = f"event-{event_id}"
            self.timestamp = None
            type(self).live += 1
            type(self).maximum_live = max(type(self).maximum_live, type(self).live)

        def __del__(self):
            type(self).live -= 1

    class StreamingGateway:
        def logs(self, _run_id, *, cursor):
            page_number = cursor // page_size
            events = tuple(TrackedEvent(cursor + offset) for offset in range(page_size))
            return SimpleNamespace(
                events=events,
                next_cursor=cursor + page_size,
                has_more=page_number + 1 < page_count,
            )

    connector = DastConnector(gateway=StreamingGateway(), output_dir=tmp_path)
    recovery_writes = []
    monkeypatch.setattr(connector, "_write_recovery", lambda recovery: recovery_writes.append(recovery.log_cursor))
    monkeypatch.setattr("builtins.print", lambda *_args, **_kwargs: None)

    recovery = connector._drain_logs(DastRecoveryState.initial(_command()).for_run("run-123"))
    gc.collect()

    assert recovery.log_cursor == page_count * page_size
    assert connector._logs_delivered == page_count * page_size
    assert len(recovery_writes) == page_count
    assert TrackedEvent.live == 0
    assert TrackedEvent.maximum_live <= page_size * 2


def test_large_result_is_rejected_from_content_length_before_body_buffering():
    iterated = False

    class OversizedResponse:
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(DastGatewayClient.MAX_RESULT_BYTES + 1),
        }

        def iter_bytes(self):
            nonlocal iterated
            iterated = True
            yield b"{}"

    with pytest.raises(DastConnectorError, match="exceeds its size limit"):
        DastGatewayClient._read_bounded_json(
            OversizedResponse(),
            limit=DastGatewayClient.MAX_RESULT_BYTES,
        )

    assert iterated is False


def test_oversized_or_untrusted_log_content_is_not_emitted(tmp_path, capsys):
    def handler(request):
        if request.method == "POST":
            return _response(202, _accepted())
        if request.url.path.endswith("/logs"):
            return _response(
                200,
                {
                    "contract_version": "2.0",
                    "events": [
                        {
                            "event_id": 0,
                            "level": "info",
                            "message": "s" * (16 * 1024 + 1),
                            "timestamp": None,
                        },
                    ],
                    "next_cursor": 1,
                    "has_more": False,
                },
            )
        return _response(200, _status("running"))

    with pytest.raises(ValueError, match="log message"):
        DastConnector(gateway=_gateway(handler), output_dir=tmp_path, sleep=lambda _seconds: None).run(
            _connector_input(),
        )

    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("status_code", "code", "retryable"),
    [
        (401, "AUTHENTICATION_FAILED", False),
        (400, "INVALID_REQUEST", False),
        (403, "POLICY_DENIED", False),
        (409, "CAPACITY_BUSY", True),
    ],
)
def test_start_preserves_typed_gateway_errors_and_only_retries_retryable_failures(
    status_code,
    code,
    retryable,
):
    """A rejection that will be repeated verbatim is not something to be patient about.

    Only the provider's own "retryable" earns a wait, and it earns the short one: no run exists
    yet, so the caller's queue is a cheaper place to wait than this process is.
    """
    attempts = []
    clock = _Clock()

    def handler(request):
        attempts.append(request)
        return _response(
            status_code,
            {
                "code": code,
                "message": "request rejected",
                "retryable": retryable,
                "correlation_id": "pipeline-123",
            },
        )

    with pytest.raises(DastGatewayError) as exc_info:
        _gateway(handler, clock=clock).start(_command())

    assert exc_info.value.error.code == code
    assert exc_info.value.error.retryable is retryable
    if not retryable:
        assert len(attempts) == 1
        assert clock.sleeps == []
    else:
        assert len(attempts) > 1
        assert sum(clock.sleeps) == pytest.approx(HANDSHAKE.window_seconds)
        assert sum(clock.sleeps) < IN_FLIGHT.window_seconds


def test_connector_rejects_invalid_terminal_payload_before_writing_result(tmp_path):
    def handler(request):
        if request.method == "POST":
            return _response(202, _accepted())
        if request.url.path.endswith("/logs"):
            return _response(200, _logs(0))
        if request.url.path.endswith("/results"):
            return _response(200, {**_result(), "legacy_report": {}})
        return _response(200, _status("succeeded", result_ready=True))

    output_dir = tmp_path / "output"
    with pytest.raises(ValueError, match="terminal result fields"):
        DastConnector(gateway=_gateway(handler), output_dir=output_dir, sleep=lambda _: None).run(
            _connector_input(),
        )

    assert not (output_dir / "result.json").exists()


def test_connector_requests_provider_stop_when_interrupted_after_acceptance(tmp_path):
    stop_calls = []

    def handler(request):
        if request.method == "POST" and request.url.path.endswith("/stop"):
            stop_calls.append(request)
            return _response(200, {**_status("stop_requested"), "stop_requested": True})
        if request.method == "POST":
            return _response(202, _accepted())
        raise KeyboardInterrupt

    result = DastConnector(
        gateway=_gateway(handler),
        output_dir=tmp_path,
        sleep=lambda _: None,
    ).run(_connector_input())

    assert result is None
    assert len(stop_calls) == 1
    recovery = DastRecoveryState.from_file(tmp_path / "recovery.json")
    assert json.loads((tmp_path / "outcome.json").read_text(encoding="utf-8")) == _outcome(
        "stop_pending",
        recovery,
        reason_code="CANCEL_REQUESTED",
    )


def test_cancel_before_start_never_creates_a_provider_run(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        raise AssertionError("gateway must not be contacted")

    connector_input = _connector_input()
    connector_input = type(connector_input)(
        gateway_url=connector_input.gateway_url,
        command=connector_input.command,
        recovery=connector_input.recovery,
        stop_requested=True,
    )
    result = DastConnector(gateway=_gateway(handler), output_dir=tmp_path).run(connector_input)

    assert result is None
    assert requests == []
    assert json.loads((tmp_path / "outcome.json").read_text(encoding="utf-8")) == _outcome(
        "cancelled_before_start",
        connector_input.recovery,
        reason_code="CANCEL_REQUESTED",
    )


def test_deadline_requests_idempotent_stop_for_known_run_and_returns_pending(tmp_path):
    stop_calls = []
    recovery = DastRecoveryState.initial(_command()).for_run("run-123").with_cursor(4)
    now = datetime(2026, 7, 26, 10, 0, tzinfo=UTC)

    def handler(request):
        if request.method == "POST" and request.url.path.endswith("/stop"):
            stop_calls.append(request)
            return _response(200, {**_status("stop_requested"), "stop_requested": True})
        if request.method == "GET" and request.url.path.endswith("/run-123"):
            return _response(200, _status("running"))
        if request.url.path.endswith("/logs"):
            assert int(request.url.params["cursor"]) == 4
            return _response(200, _logs(4))
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    connector_input = _connector_input(recovery=recovery)
    connector_input = type(connector_input)(
        gateway_url=connector_input.gateway_url,
        command=connector_input.command,
        recovery=recovery,
        deadline_at=(now - timedelta(seconds=1)).isoformat(),
    )
    result = DastConnector(
        gateway=_gateway(handler),
        output_dir=tmp_path,
        now=lambda: now,
    ).run(connector_input)

    assert result is None
    assert len(stop_calls) == 1
    assert json.loads((tmp_path / "outcome.json").read_text(encoding="utf-8")) == _outcome(
        "stop_pending",
        recovery,
        reason_code="EXECUTION_TIMEOUT",
    )


def test_a_run_that_already_finished_is_collected_instead_of_stopped(tmp_path):
    """Reaching for ``/stop`` first left a finished run's result unfetched and reported as pending."""
    recovery = DastRecoveryState.initial(_command()).for_run("run-123")
    stop_calls = []

    def handler(request):
        if request.method == "POST" and request.url.path.endswith("/stop"):
            stop_calls.append(request)
            return _response(200, {**_status("stop_requested"), "stop_requested": True})
        if request.method == "GET" and request.url.path.endswith("/run-123"):
            return _response(200, _status("succeeded", result_ready=True))
        if request.url.path.endswith("/logs"):
            return _response(200, _logs(0, message="closing sequence complete"))
        if request.url.path.endswith("/results"):
            return _response(200, _result())
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    now = datetime(2026, 7, 26, 10, 0, tzinfo=UTC)
    connector_input = _connector_input(recovery=recovery)
    connector_input = type(connector_input)(
        gateway_url=connector_input.gateway_url,
        command=connector_input.command,
        recovery=recovery,
        deadline_at=(now - timedelta(seconds=1)).isoformat(),
    )
    result = DastConnector(
        gateway=_gateway(handler),
        output_dir=tmp_path,
        now=lambda: now,
    ).run(connector_input)

    assert result is not None
    assert result.status == "succeeded"
    assert stop_calls == []
    assert json.loads((tmp_path / "outcome.json").read_text(encoding="utf-8"))["state"] == "terminal"
    assert json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))["status"] == "succeeded"


def test_stop_response_that_turns_terminal_is_still_collected(tmp_path):
    """The run can finish between the status read and the stop, so both answers must be honoured."""
    recovery = DastRecoveryState.initial(_command()).for_run("run-123")

    def handler(request):
        if request.method == "POST" and request.url.path.endswith("/stop"):
            return _response(
                200,
                {
                    **_status("stopped", result_ready=True),
                    "stop_requested": True,
                },
            )
        if request.method == "GET" and request.url.path.endswith("/run-123"):
            return _response(200, _status("running"))
        if request.url.path.endswith("/logs"):
            return _response(200, _logs(0, message="provider stopped"))
        if request.url.path.endswith("/results"):
            return _response(200, _result(status="stopped"))
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    connector_input = _connector_input(recovery=recovery)
    connector_input = type(connector_input)(
        gateway_url=connector_input.gateway_url,
        command=connector_input.command,
        recovery=recovery,
        stop_requested=True,
    )
    result = DastConnector(gateway=_gateway(handler), output_dir=tmp_path).run(connector_input)

    assert result is not None
    assert result.status == "stopped"
    assert json.loads((tmp_path / "outcome.json").read_text(encoding="utf-8"))["state"] == "terminal"


def test_harvest_only_collects_a_finished_run_without_starting_or_stopping_anything(tmp_path):
    """The last look taken before the platform gives a run up for lost."""
    recovery = DastRecoveryState.initial(_command()).for_run("run-123").with_cursor(784)
    forbidden = []

    def handler(request):
        if request.method == "POST":
            forbidden.append(request)
            raise AssertionError("harvest must neither start nor stop a run")
        if request.url.path.endswith("/logs"):
            return _response(200, _logs(784))
        if request.url.path.endswith("/results"):
            return _response(200, _result())
        if request.url.path.endswith("/run-123"):
            return _response(200, _status("succeeded", result_ready=True))
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    connector_input = _connector_input(recovery=recovery)
    connector_input = type(connector_input)(
        gateway_url=connector_input.gateway_url,
        command=connector_input.command,
        recovery=recovery,
        harvest_only=True,
    )
    result = DastConnector(gateway=_gateway(handler), output_dir=tmp_path).run(connector_input)

    assert result is not None
    assert result.status == "succeeded"
    assert forbidden == []
    assert json.loads((tmp_path / "outcome.json").read_text(encoding="utf-8"))["state"] == "terminal"


def test_harvest_only_reports_a_run_that_is_still_not_terminal(tmp_path):
    recovery = DastRecoveryState.initial(_command()).for_run("run-123")

    def handler(request):
        if request.method == "POST":
            raise AssertionError("harvest must neither start nor stop a run")
        if request.url.path.endswith("/logs"):
            return _response(200, _logs(0))
        if request.url.path.endswith("/run-123"):
            return _response(200, _status("running"))
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    connector_input = _connector_input(recovery=recovery)
    connector_input = type(connector_input)(
        gateway_url=connector_input.gateway_url,
        command=connector_input.command,
        recovery=recovery,
        harvest_only=True,
    )
    result = DastConnector(gateway=_gateway(handler), output_dir=tmp_path).run(connector_input)

    assert result is None
    assert json.loads((tmp_path / "outcome.json").read_text(encoding="utf-8"))["state"] == "stop_pending"
    assert not (tmp_path / "result.json").exists()


def test_harvest_only_without_a_provider_run_contacts_nobody(tmp_path):
    def handler(request):
        raise AssertionError(f"gateway must not be contacted: {request.method} {request.url.path}")

    connector_input = _connector_input()
    connector_input = type(connector_input)(
        gateway_url=connector_input.gateway_url,
        command=connector_input.command,
        recovery=connector_input.recovery,
        harvest_only=True,
    )
    result = DastConnector(gateway=_gateway(handler), output_dir=tmp_path).run(connector_input)

    assert result is None
    assert json.loads((tmp_path / "outcome.json").read_text(encoding="utf-8"))["state"] == (
        "cancelled_before_start"
    )


def test_gateway_client_configures_tls_timeouts_limits_and_disables_environment(monkeypatch, tmp_path):
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("test CA", encoding="utf-8")
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def close(self):
            pass

    monkeypatch.setattr("pipeline.dast.connector.httpx.Client", FakeClient)

    with DastGatewayClient(
        gateway_url="https://dast.internal",
        token="public.secret",
        ca_file=ca_file,
        resolver=lambda _hostname, _port: ("8.8.8.8",),
    ):
        pass

    assert captured["verify"] == str(ca_file)
    assert captured["follow_redirects"] is False
    assert captured["trust_env"] is False
    assert captured["timeout"].connect == pytest.approx(5.0)
    assert captured["timeout"].read == pytest.approx(30.0)
    assert captured["limits"].max_connections == 4


def test_gateway_allows_private_destination_only_inside_trusted_vpn_namespace():
    def private_resolver(_hostname, _port):
        return ("10.23.4.5",)

    with pytest.raises(DastConnectorError, match="require a trusted VPN route"):
        DastGatewayClient(
            gateway_url="https://dast.internal",
            token="public.secret",
            resolver=private_resolver,
            client=httpx.Client(transport=httpx.MockTransport(lambda _request: _response(200, {}))),
        )

    client = httpx.Client(transport=httpx.MockTransport(lambda _request: _response(200, {})))
    with DastGatewayClient(
        gateway_url="https://dast.internal",
        token="public.secret",
        trusted_vpn=True,
        resolver=private_resolver,
        client=client,
    ):
        pass


def test_gateway_rejects_loopback_even_inside_trusted_vpn_namespace():
    with pytest.raises(DastConnectorError, match="forbidden local"):
        DastGatewayClient(
            gateway_url="https://dast.internal",
            token="public.secret",
            trusted_vpn=True,
            resolver=lambda _hostname, _port: ("127.0.0.1",),
            client=httpx.Client(transport=httpx.MockTransport(lambda _request: _response(200, {}))),
        )


def _handoff(tmp_path, *, payload=None):
    token = tmp_path / "token"
    token.write_text("public.secret", encoding="utf-8")
    token.chmod(0o600)
    input_path = tmp_path / "input.json"
    if payload is not None:
        input_path.write_text(payload, encoding="utf-8")
    return input_path, token, tmp_path / "output"


def test_a_mount_the_daemon_replaced_with_an_empty_directory_exits_as_local_setup(tmp_path):
    """Docker leaves a directory where a bind source did not exist; that is not a provider outage."""
    input_path, token, output = _handoff(tmp_path)
    input_path.mkdir()

    assert main(["--input", str(input_path), "--output", str(output), "--token-file", str(token)]) == (
        CONNECTOR_EXIT_LOCAL_SETUP
    )


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the mode bits this case depends on")
def test_a_handoff_written_for_another_user_exits_as_local_setup(tmp_path):
    input_path, token, output = _handoff(tmp_path, payload="{}")
    input_path.chmod(0o000)

    assert main(["--input", str(input_path), "--output", str(output), "--token-file", str(token)]) == (
        CONNECTOR_EXIT_LOCAL_SETUP
    )


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the mode bits this case depends on")
def test_an_output_directory_it_cannot_write_exits_before_the_provider_accepts_a_run(tmp_path):
    """Otherwise the provider starts a scan no one can ever check point or resume."""
    payload = json.dumps(
        DastConnectorInput(
            gateway_url="https://dast.internal",
            command=_command(),
            recovery=DastRecoveryState.initial(_command()),
        ).to_wire()
    )
    input_path, token, _ = _handoff(tmp_path, payload=payload)
    output = tmp_path / "readonly" / "output"
    output.parent.mkdir()
    output.parent.chmod(0o500)

    try:
        assert main(["--input", str(input_path), "--output", str(output), "--token-file", str(token)]) == (
            CONNECTOR_EXIT_LOCAL_SETUP
        )
    finally:
        output.parent.chmod(0o700)


def test_a_gateway_blip_while_polling_is_waited_out_instead_of_ending_the_watch(tmp_path):
    """
    The incident this behaviour exists for.

    A watch that had been running for over an hour ended because the tunnel to the gateway
    dropped for about two minutes: three instant failures spent the whole retry allowance in
    under two seconds, the container died, the sidecar was torn down and the platform had to
    resume the run from its checkpoint. The scan itself never stopped -- only the watch did.
    """
    status_calls = {"count": 0}
    clock = _Clock()

    def handler(request):
        if request.method == "POST":
            return _response(202, _accepted())
        if request.url.path.endswith("/logs"):
            return _response(200, _logs(0))
        if request.url.path.endswith("/results"):
            return _response(200, _result())
        status_calls["count"] += 1
        if status_calls["count"] in (2, 3):
            raise httpx.ConnectError("connection to dast.internal:443 refused", request=request)
        if status_calls["count"] == 1:
            return _response(200, _status("running"))
        return _response(200, _status("succeeded", result_ready=True))

    result = DastConnector(
        gateway=_gateway(handler, clock=clock),
        output_dir=tmp_path,
        poll_interval=0,
        sleep=lambda _seconds: None,
    ).run(_connector_input())

    assert result is not None
    assert (tmp_path / "result.json").exists()
    # Two waits, and the watch carried on: no exception, no lost run, no resumed attempt.
    assert clock.sleeps == [1.0, 2.0]


def test_patience_is_per_call_so_a_link_that_keeps_flapping_never_runs_out(tmp_path):
    """A link that recovers repeatedly is a working link, however often it drops.

    Each answered call restores the full allowance, so the total waiting across a long watch is
    free to exceed any single window -- what must not happen is giving up on a provider that is
    still answering.
    """
    outage = {"failures_left": 9}
    rounds = {"answered": 0}
    clock = _Clock()

    def handler(request):
        if request.method == "POST":
            return _response(202, _accepted())
        if request.url.path.endswith("/logs"):
            return _response(200, _logs(0))
        if request.url.path.endswith("/results"):
            return _response(200, _result())
        if outage["failures_left"] > 0:
            outage["failures_left"] -= 1
            raise httpx.ConnectError("tunnel flapping", request=request)
        rounds["answered"] += 1
        if rounds["answered"] < 5:
            outage["failures_left"] = 9
            return _response(200, _status("running"))
        return _response(200, _status("succeeded", result_ready=True))

    result = DastConnector(
        gateway=_gateway(handler, clock=clock),
        output_dir=tmp_path,
        poll_interval=0,
        sleep=lambda _seconds: None,
    ).run(_connector_input())

    assert result is not None
    assert rounds["answered"] == 5
    assert sum(clock.sleeps) > IN_FLIGHT.window_seconds


def test_giving_up_names_the_transport_failure_and_not_the_gateway_it_reached_for():
    """
    Every one of these failures used to print the same line.

    "unreachable" cannot tell a refused connection from a name that will not resolve from a read
    that timed out, and the three need different repairs -- the last outage had to be classified
    from container exit timings instead. The deployment's own address stays out of it: the
    pipeline log is tenant-readable.
    """
    def handler(request):
        raise httpx.ConnectError("connection to dast.internal:443 refused", request=request)

    with pytest.raises(DastConnectorError) as exc_info:
        _gateway(handler).start(_command())

    message = str(exc_info.value)
    assert "unreachable" in message
    assert "ConnectError" in message
    assert "refused" in message
    assert "dast.internal" not in message


def test_no_patience_outlives_the_runs_own_ceiling():
    clock = _Clock()

    def handler(request):
        raise httpx.ConnectError("tunnel down", request=request)

    with pytest.raises(DastConnectorError, match="unreachable"):
        _gateway(handler, clock=clock, may_retry=lambda: False).status("run-123")

    assert clock.sleeps == []


def test_a_harvest_or_a_cancellation_does_not_inherit_the_watching_patience(monkeypatch, tmp_path):
    """Both run while somebody is waiting: a harvest is the last look before a run is abandoned,
    and a cancellation has an operator behind it. Only a live watch is worth minutes."""
    plans = []

    class _RecordingClient:
        def __init__(self, **kwargs):
            plans.append(kwargs["plan"])

        def __enter__(self):
            return self

        def __exit__(self, *_exc_info):
            return None

    monkeypatch.setattr(connector_module, "DastGatewayClient", _RecordingClient)
    monkeypatch.setattr(connector_module.DastConnector, "run", lambda self, _connector_input: None)

    for index, invocation in enumerate(({}, {"harvest_only": True}, {"stop_requested": True})):
        case = tmp_path / f"case{index}"
        case.mkdir()
        payload = json.dumps(
            DastConnectorInput(
                gateway_url="https://dast.internal",
                command=_command(),
                recovery=DastRecoveryState.initial(_command()),
                **invocation,
            ).to_wire(),
        )
        input_path, token, output = _handoff(case, payload=payload)
        assert main(["--input", str(input_path), "--output", str(output), "--token-file", str(token)]) == 0

    assert plans == [WATCH, IMPATIENT, IMPATIENT]
