"""Tests for ``pipeline.bridge_client.BridgeClient``.

Covers both endpoints (``/analyze`` async, ``/analyze-sync`` sync), the
error-swallowing semantics that the analyzer-runner failure-handling
contract relies on, and the construction-time socket-path / timeout
plumbing so AIST callers get correct values from Django settings.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx

from pipeline.bridge_client import (
    DEFAULT_SOCKET_PATH,
    DEFAULT_SYNC_TIMEOUT_SECONDS,
    BridgeClient,
)


def _make_response(status_code=200, payload=None):
    resp = MagicMock()
    resp.status_code = status_code
    if payload is not None:
        resp.json.return_value = payload
        resp.text = json.dumps(payload)
    else:
        resp.text = ""
    if status_code >= 400:
        # `raise_for_status` is only used by analyze_async — make it actually raise.
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=MagicMock(), response=resp,
        )
    return resp


def _patched_client(response=None, raise_exc=None):
    """Yield a patch context that intercepts httpx.Client construction."""
    fake_client = MagicMock()
    if raise_exc is not None:
        return patch(
            "pipeline.bridge_client.httpx.Client",
            side_effect=raise_exc,
        )
    if response is not None:
        fake_client.return_value.__enter__.return_value.post.return_value = response
    return patch(
        "pipeline.bridge_client.httpx.Client",
        return_value=fake_client.return_value,
    )


# ─────────────────────────────────────────────────────────────────────────────
# /analyze-sync
# ─────────────────────────────────────────────────────────────────────────────

def test_analyze_sync_posts_full_payload_and_returns_body():
    response = _make_response(payload={"status": "success", "detail": ""})
    with patch("pipeline.bridge_client.httpx.Client") as fake_client:
        fake_client.return_value.__enter__.return_value.post.return_value = response

        client = BridgeClient(socket_path="/tmp/test.sock")
        body = client.analyze_sync(
            skill_name="aist-diff-security-review",
            project_id="pipe-1",
            source_path="/tmp/proj",
            extra_args="output_path=/tmp/out runtime_filename=runtime.json",
        )

    assert body == {"status": "success", "detail": ""}
    instance = fake_client.return_value.__enter__.return_value
    call = instance.post.call_args
    assert call.args[0] == "http://localhost/analyze-sync"
    payload = call.kwargs["json"]
    assert payload == {
        "skill_name": "aist-diff-security-review",
        "project_id": "pipe-1",
        "source_path": "/tmp/proj",
        "callback_url": "",
        "extra_args": "output_path=/tmp/out runtime_filename=runtime.json",
        # No auth_env passed at construction → empty subprocess_env in body.
        # The field is generic and bridge-side defaults to {} when missing,
        # so this is forward-compat with older bridges that pre-date Task 4.
        "subprocess_env": {},
    }


def test_analyze_sync_returns_error_dict_on_non_200():
    response = _make_response(status_code=500, payload={"status": "error", "detail": "x"})
    with patch("pipeline.bridge_client.httpx.Client") as fake_client:
        fake_client.return_value.__enter__.return_value.post.return_value = response

        client = BridgeClient(socket_path="/tmp/test.sock")
        body = client.analyze_sync(
            skill_name="s",
            project_id="p",
            source_path="/tmp/proj",
        )
    assert body["status"] == "error"


def test_analyze_sync_returns_error_dict_on_non_json_body():
    response = MagicMock()
    response.status_code = 200
    response.json.side_effect = ValueError("not json")
    response.text = "<html>?</html>"
    with patch("pipeline.bridge_client.httpx.Client") as fake_client:
        fake_client.return_value.__enter__.return_value.post.return_value = response

        client = BridgeClient(socket_path="/tmp/test.sock")
        body = client.analyze_sync(skill_name="s", project_id="p", source_path="/x")
    assert body["status"] == "error"
    assert "non-json" in body["detail"]


def test_analyze_sync_returns_error_dict_on_connection_error():
    with patch(
        "pipeline.bridge_client.httpx.Client",
        side_effect=httpx.ConnectError("socket missing"),
    ):
        client = BridgeClient(socket_path="/tmp/test.sock")
        body = client.analyze_sync(skill_name="s", project_id="p", source_path="/x")
    assert body["status"] == "error"
    assert "transport error" in body["detail"]


def test_analyze_sync_returns_error_dict_on_oserror():
    with patch(
        "pipeline.bridge_client.httpx.Client",
        side_effect=OSError("no such file"),
    ):
        client = BridgeClient(socket_path="/tmp/test.sock")
        body = client.analyze_sync(skill_name="s", project_id="p", source_path="/x")
    assert body["status"] == "error"
    assert "socket error" in body["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# /analyze (existing local triage path)
# ─────────────────────────────────────────────────────────────────────────────

def test_analyze_async_posts_to_analyze_endpoint_with_callback_url():
    response = _make_response(payload={"accepted": True})
    response.status_code = 202
    with patch("pipeline.bridge_client.httpx.Client") as fake_client:
        fake_client.return_value.__enter__.return_value.post.return_value = response

        client = BridgeClient(socket_path="/tmp/test.sock")
        client.analyze_async(
            skill_name="aist-finding-triage",
            project_id="pipe-async",
            source_path="/tmp/proj",
            callback_url="https://callback.example/triage/abc",
        )
    instance = fake_client.return_value.__enter__.return_value
    call = instance.post.call_args
    assert call.args[0] == "http://localhost/analyze"
    payload = call.kwargs["json"]
    assert payload["callback_url"] == "https://callback.example/triage/abc"


def test_analyze_async_raises_bridge_error_on_http_error():
    # The local triage flow needs the exception to propagate so it can
    # finish_pipeline(degraded=True). Silent failure would leave the
    # pipeline stuck in PUSH_TO_AI forever.
    from pipeline.bridge_client import BridgeError
    response = _make_response(status_code=500)
    with patch("pipeline.bridge_client.httpx.Client") as fake_client:
        fake_client.return_value.__enter__.return_value.post.return_value = response
        client = BridgeClient(socket_path="/tmp/test.sock")
        try:
            client.analyze_async(skill_name="s", project_id="p", source_path="/x")
        except BridgeError:
            pass
        else:
            raise AssertionError("BridgeError not raised on HTTP 500")


def test_analyze_async_raises_bridge_error_on_connection_error():
    from pipeline.bridge_client import BridgeError
    with patch(
        "pipeline.bridge_client.httpx.Client",
        side_effect=httpx.ConnectError("bridge gone"),
    ):
        client = BridgeClient(socket_path="/tmp/test.sock")
        try:
            client.analyze_async(skill_name="s", project_id="p", source_path="/x")
        except BridgeError:
            pass
        else:
            raise AssertionError("BridgeError not raised on connect failure")


# ─────────────────────────────────────────────────────────────────────────────
# Construction
# ─────────────────────────────────────────────────────────────────────────────

def test_default_socket_path_matches_compose_volume():
    # docker-compose mounts the bridge UDS at /run/claude-bridge/bridge.sock
    # in both the bridge and uwsgi services. Drift here breaks every caller.
    assert DEFAULT_SOCKET_PATH == "/run/claude-bridge/bridge.sock"


def test_socket_path_is_passed_to_transport():
    captured: dict = {}

    def fake_transport(*args, **kwargs):
        captured["uds"] = kwargs.get("uds")
        return MagicMock()

    response = _make_response(payload={"status": "success"})
    with patch("pipeline.bridge_client.httpx.HTTPTransport", side_effect=fake_transport), \
         patch("pipeline.bridge_client.httpx.Client") as fake_client:
        fake_client.return_value.__enter__.return_value.post.return_value = response
        BridgeClient(socket_path="/var/run/custom.sock").analyze_sync(
            skill_name="s", project_id="p", source_path="/x",
        )
    assert captured["uds"] == "/var/run/custom.sock"


def test_sync_timeout_default_is_safe():
    # Bridge enforces TRIAGE_TIMEOUT (1800s) internally; the client's HTTP
    # timeout MUST be larger so we don't read-time-out before the bridge does.
    assert DEFAULT_SYNC_TIMEOUT_SECONDS > 1800


# ─────────────────────────────────────────────────────────────────────────────
# auth_env passthrough (Task 5)
# ─────────────────────────────────────────────────────────────────────────────


def test_analyze_sync_forwards_auth_env_as_subprocess_env():
    """A generic ``auth_env`` kwarg at construction time must surface in the
    POST body under the bridge's generic ``subprocess_env`` field.

    Invariant I2 — neither parameter name contains "claude" / "oauth" /
    "anthropic"; the bridge is agent-agnostic at this layer.
    """
    response = _make_response(payload={"status": "success", "detail": ""})
    with patch("pipeline.bridge_client.httpx.Client") as fake_client:
        fake_client.return_value.__enter__.return_value.post.return_value = response

        client = BridgeClient(
            socket_path="/tmp/test.sock",
            auth_env={"CLAUDE_CODE_OAUTH_TOKEN": "oat_xxx"},
        )
        client.analyze_sync(skill_name="s", project_id="p", source_path="/x")

    instance = fake_client.return_value.__enter__.return_value
    call = instance.post.call_args
    payload = call.kwargs["json"]
    assert payload["subprocess_env"] == {"CLAUDE_CODE_OAUTH_TOKEN": "oat_xxx"}


def test_analyze_async_forwards_auth_env_as_subprocess_env():
    response = _make_response(payload={"accepted": True})
    response.status_code = 202
    with patch("pipeline.bridge_client.httpx.Client") as fake_client:
        fake_client.return_value.__enter__.return_value.post.return_value = response

        client = BridgeClient(
            socket_path="/tmp/test.sock",
            auth_env={"CLAUDE_CODE_OAUTH_TOKEN": "oat_yyy"},
        )
        client.analyze_async(
            skill_name="aist-finding-triage",
            project_id="p-async",
            source_path="/x",
            callback_url="",
        )

    instance = fake_client.return_value.__enter__.return_value
    payload = instance.post.call_args.kwargs["json"]
    assert payload["subprocess_env"] == {"CLAUDE_CODE_OAUTH_TOKEN": "oat_yyy"}


def test_no_auth_env_omits_subprocess_env_or_sends_empty_dict():
    """Without auth_env the field is an empty dict (not absent).

    Either form is valid for the bridge (Pydantic Field default), but the
    client picks one and sticks with it for test determinism. Empty dict
    is preferred — keeps the payload shape constant across runs.
    """
    response = _make_response(payload={"status": "success"})
    with patch("pipeline.bridge_client.httpx.Client") as fake_client:
        fake_client.return_value.__enter__.return_value.post.return_value = response

        client = BridgeClient(socket_path="/tmp/test.sock")
        client.analyze_sync(skill_name="s", project_id="p", source_path="/x")

    payload = (
        fake_client.return_value.__enter__.return_value.post.call_args.kwargs["json"]
    )
    assert payload["subprocess_env"] == {}


def test_auth_env_keys_logged_but_values_never_logged(caplog=None):
    """Defence in depth — if the bridge HTTP call fails and we log the
    failure, the token value MUST NOT appear in any log record.

    The client may legitimately log the *keys* (so operators can see
    "we tried to inject CLAUDE_CODE_OAUTH_TOKEN") but never the values.
    """
    import logging

    records: list[str] = []

    class _Sink(logging.Handler):
        def emit(self, rec):
            records.append(rec.getMessage())

    target = logging.getLogger("pipeline.bridge_client")
    sink = _Sink()
    target.addHandler(sink)
    try:
        with patch(
            "pipeline.bridge_client.httpx.Client",
            side_effect=httpx.ConnectError("socket missing"),
        ):
            client = BridgeClient(
                socket_path="/tmp/test.sock",
                auth_env={"CLAUDE_CODE_OAUTH_TOKEN": "oat_TOP_SECRET_VALUE"},
            )
            client.analyze_sync(skill_name="s", project_id="p", source_path="/x")
    finally:
        target.removeHandler(sink)

    for line in records:
        assert "oat_TOP_SECRET_VALUE" not in line, f"secret leaked: {line!r}"
