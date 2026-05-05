"""
Single-source-of-truth client for the aist-triage-bridge HTTP API.

The bridge exposes two endpoints over a Unix domain socket:

- ``POST /analyze`` — fire-and-forget. Used by AIST's existing local-triage
  flow (``aist/tasks/ai.py``); the bridge returns 202 and later POSTs the
  result to ``callback_url``.

- ``POST /analyze-sync`` — blocks until the skill finishes. Used by the
  SAST pipeline's agent-bridge analyzers (``agent_bridge_runner``) so
  the result file is on disk before ``upload_results_internal`` reads it.

Both flows share socket discovery, payload shape, error handling, and
(future) auth. Keeping this in one place means a single change point for
those concerns. The class is Django-agnostic — callers in AIST construct
it with values from Django settings, callers inside sast-pipeline can
construct it with raw env values.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

log = logging.getLogger(__name__)

DEFAULT_SOCKET_PATH = "/run/claude-bridge/bridge.sock"
DEFAULT_ASYNC_TIMEOUT_SECONDS = 10
# Keep in sync with AIST_LOCAL_TRIAGE_TIMEOUT in aist-triage-bridge (default 10800s = 3h).
# The +60s buffer ensures the bridge always returns a result before the HTTP client gives up.
DEFAULT_SYNC_TIMEOUT_SECONDS = int(os.environ.get("AIST_LOCAL_TRIAGE_TIMEOUT", "10800")) + 60

_BRIDGE_BASE_URL = "http://localhost"
_ANALYZE_PATH = "/analyze"
_ANALYZE_SYNC_PATH = "/analyze-sync"


class BridgeError(Exception):
    """Raised by analyze_sync on transport failure when the caller wants to abort."""


class BridgeClient:

    """Sync HTTP client for the aist-triage-bridge UDS API."""

    def __init__(
        self,
        *,
        socket_path: str = DEFAULT_SOCKET_PATH,
        sync_timeout_seconds: int = DEFAULT_SYNC_TIMEOUT_SECONDS,
        async_timeout_seconds: int = DEFAULT_ASYNC_TIMEOUT_SECONDS,
    ) -> None:
        self._socket_path = socket_path
        self._sync_timeout = sync_timeout_seconds
        self._async_timeout = async_timeout_seconds

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def analyze_async(
        self,
        *,
        skill_name: str,
        project_id: str,
        source_path: str,
        callback_url: str = "",
        extra_args: str = "",
    ) -> int:
        """Fire-and-forget POST to ``/analyze``.

        The bridge returns 202 and POSTs the eventual result to
        ``callback_url`` (or just runs to completion if no callback is set).

        Raises ``BridgeError`` on transport failure so the caller's pipeline
        state machine can mark its run degraded. Used by AIST's local
        triage flow (``aist/tasks/ai.py``); the SAST-pipeline diff
        analyzer goes through ``analyze_sync`` which swallows errors
        instead.
        """
        payload = self._payload(
            skill_name=skill_name,
            project_id=project_id,
            source_path=source_path,
            callback_url=callback_url,
            extra_args=extra_args,
        )
        try:
            with self._client(timeout=self._async_timeout) as client:
                resp = client.post(_BRIDGE_BASE_URL + _ANALYZE_PATH, json=payload)
                resp.raise_for_status()
            return resp.status_code
        except httpx.HTTPError as exc:
            log.warning(
                "Bridge /analyze skill=%s pipeline=%s failed: %s",
                skill_name, project_id, exc,
            )
            msg = f"bridge /analyze transport error: {exc}"
            raise BridgeError(msg) from exc
        except OSError as exc:
            log.warning(
                "Bridge /analyze skill=%s pipeline=%s socket error on %s: %s",
                skill_name, project_id, self._socket_path, exc,
            )
            msg = f"bridge /analyze socket error: {exc}"
            raise BridgeError(msg) from exc

    def analyze_sync(
        self,
        *,
        skill_name: str,
        project_id: str,
        source_path: str,
        extra_args: str = "",
    ) -> dict[str, Any]:
        """Block until ``/analyze-sync`` returns the bridge's CallbackPayload.

        Returns the parsed JSON body (``{"status": ..., "detail": ...}``)
        on HTTP 200. Returns a synthetic ``{"status": "error", "detail": ...}``
        when the call fails in any way — failures are logged but never
        raised, matching how docker-analyzer failures are handled in
        ``analyzer_runner``.
        """
        payload = self._payload(
            skill_name=skill_name,
            project_id=project_id,
            source_path=source_path,
            callback_url="",
            extra_args=extra_args,
        )
        try:
            with self._client(timeout=self._sync_timeout) as client:
                resp = client.post(_BRIDGE_BASE_URL + _ANALYZE_SYNC_PATH, json=payload)
            if resp.status_code != 200:
                detail = resp.text[:500] if resp.text else f"HTTP {resp.status_code}"
                log.warning(
                    "Bridge /analyze-sync skill=%s pipeline=%s returned HTTP %s: %s",
                    skill_name, project_id, resp.status_code, detail,
                )
                return {"status": "error", "detail": detail}
            try:
                body = resp.json()
            except ValueError:
                log.warning(
                    "Bridge /analyze-sync skill=%s returned non-JSON body",
                    skill_name,
                )
                return {"status": "error", "detail": "non-json bridge response"}
            self._log_outcome(skill_name, project_id, body)
            return body
        except httpx.HTTPError as exc:
            log.warning(
                "Bridge /analyze-sync skill=%s pipeline=%s failed: %s",
                skill_name, project_id, exc,
            )
            return {"status": "error", "detail": f"transport error: {exc}"[:500]}
        except OSError as exc:
            # Most commonly: socket missing because the bridge container is down.
            log.warning(
                "Bridge /analyze-sync skill=%s pipeline=%s socket error on %s: %s",
                skill_name, project_id, self._socket_path, exc,
            )
            return {"status": "error", "detail": f"socket error: {exc}"[:500]}

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _payload(
        *,
        skill_name: str,
        project_id: str,
        source_path: str,
        callback_url: str,
        extra_args: str,
    ) -> dict[str, str]:
        return {
            "skill_name": skill_name,
            "project_id": project_id,
            "source_path": source_path,
            "callback_url": callback_url,
            "extra_args": extra_args,
        }

    def _client(self, *, timeout: int) -> httpx.Client:
        transport = httpx.HTTPTransport(uds=self._socket_path)
        return httpx.Client(transport=transport, timeout=timeout)

    @staticmethod
    def _log_outcome(skill_name: str, project_id: str, body: dict) -> None:
        status = body.get("status")
        detail = body.get("detail", "") or ""
        if status == "success":
            log.info(
                "Bridge /analyze-sync skill=%s pipeline=%s succeeded",
                skill_name, project_id,
            )
        else:
            log.warning(
                "Bridge /analyze-sync skill=%s pipeline=%s status=%s detail=%s",
                skill_name, project_id, status, detail[:500],
            )
