"""Run ``type: agent-bridge`` analyzers from the host orchestrator.

Agent analyzers cannot run inside the builder container when their bridge
socket lives on the host. ``analyzer_runner`` skips these entries; this
module is invoked from ``project_builder.configure_project_run_analyses``
after the builder container finishes, so agent result files land in the
same ``output_dir`` that AIST imports later.

The public contract is the returned analyzer outcome list. Callers should
not inspect agent-specific side files; this module normalizes bridge
success/failure, truncation markers, and missing result files into a
single outcome schema.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from .bridge_client import BridgeClient

log = logging.getLogger(__name__)

AGENT_BRIDGE_TYPE = "agent-bridge"
_RUNTIME_FILENAME_SUFFIX = "_runtime.json"
_FORBIDDEN_EXTRA_ARG_CHARS = ("\n", "\r")


def _derive_ai_response_filename(result_filename: str) -> str:
    """Map ``foo_result.json`` to ``foo_ai_response.json``.

    Falls back to appending ``_ai_response.json`` to the stem when the
    convention isn't followed.
    """
    suffix = "_result.json"
    if result_filename.endswith(suffix):
        return result_filename[: -len(suffix)] + "_ai_response.json"
    stem = result_filename.rsplit(".", 1)[0]
    return f"{stem}_ai_response.json"


def _runtime_filename_for(analyzer_name: str) -> str:
    return f"{analyzer_name}{_RUNTIME_FILENAME_SUFFIX}"


def _format_extra_args(values: Mapping[str, str]) -> str:
    """Render a flat ``key=value`` string the bridge appends to the skill prompt.

    Values containing newlines are dropped — they would corrupt the
    ``extra_args`` encoding and could be used to inject prompt content.
    JSON-valued runtime config is NOT passed through this helper; it lives
    in the sidecar file referenced by ``runtime_filename``.
    """
    parts: list[str] = []
    for key, value in values.items():
        if value is None:
            continue
        text = str(value)
        if any(ch in text for ch in _FORBIDDEN_EXTRA_ARG_CHARS):
            log.warning("Dropping extra_arg %s with forbidden control character", key)
            continue
        parts.append(f"{key}={text}")
    return " ".join(parts)


def _write_runtime_file(
    *,
    output_dir: str,
    runtime_filename: str,
    runtime_env: Mapping[str, object],
) -> None:
    path = Path(output_dir) / runtime_filename
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(runtime_env), indent=2), encoding="utf-8")
    tmp.replace(path)
    # The host orchestrator runs as root; the bridge container runs as an
    # unprivileged user (uid=1000). Make output_dir world-writable so the
    # bridge can write result files without needing elevated privileges.
    try:
        os.chmod(str(path.parent), 0o777)
    except OSError as exc:
        log.warning("Could not chmod output_dir %s: %s", path.parent, exc)


def _message(*, level: str, code: str, text: object) -> dict[str, str]:
    return {"level": level, "code": code, "text": str(text or "")[:2000]}


def _ai_response_artifact(analyzer: Mapping[str, object], result_filename: str) -> dict | None:
    artifacts = analyzer.get("artifacts")
    if isinstance(artifacts, dict):
        ai_response = artifacts.get("ai_response")
        if isinstance(ai_response, dict):
            return dict(ai_response)
    return None


def _truncation_marker_path(
    *,
    analyzer: Mapping[str, object],
    output_dir: str,
    analyzer_name: str,
) -> Path:
    marker = analyzer.get("truncation_file") or f"{analyzer_name}_truncated.flag"
    return Path(output_dir) / str(marker)


def _build_outcome(
    *,
    analyzer: Mapping[str, object],
    output_dir: str,
    status: str,
    messages: list[dict[str, str]] | None = None,
) -> dict:
    name = str(analyzer.get("name") or "agent-bridge")
    result_filename = str(analyzer.get("result_file") or f"{name}_result.json")
    result_exists = (Path(output_dir) / result_filename).exists()
    required_result = bool(analyzer.get("required_result", False))
    outcome_messages = list(messages or [])

    truncation_marker = _truncation_marker_path(
        analyzer=analyzer,
        output_dir=output_dir,
        analyzer_name=name,
    )
    if truncation_marker.exists():
        status = "truncated"
        detail = truncation_marker.read_text(encoding="utf-8", errors="replace").strip()
        outcome_messages.append(_message(level="warning", code="truncated", text=detail or "Analyzer truncated input."))

    if status == "success" and required_result and not result_exists:
        status = "missing_result"
        outcome_messages.append(
            _message(
                level="warning",
                code="missing_result",
                text=f"Required analyzer result file was not produced: {result_filename}",
            ),
        )

    degraded = status in {"failed", "missing_result", "truncated"} and required_result
    return {
        "name": name,
        "type": AGENT_BRIDGE_TYPE,
        "status": status,
        "degraded": degraded,
        "required_result": required_result,
        "result_file": result_filename,
        "result_exists": result_exists,
        "messages": outcome_messages,
        "artifacts": analyzer.get("artifacts") or {},
    }


def run_agent_bridge_analyzers(
    *,
    bridge_client: BridgeClient,
    config_path: str,
    pipeline_id: str,
    project_path: str,
    output_dir: str,
    runtime_env: Mapping[str, object] | None = None,
) -> list[dict]:
    """Iterate the prepared analyzer config and invoke the bridge for each
    agent-bridge entry. Failures are normalized into analyzer outcomes.

    For each enabled ``type: agent-bridge`` analyzer this writes
    ``<output_dir>/<name>_runtime.json`` with the caller-supplied
    ``runtime_env`` and tells the skill where to find it via
    ``extra_args``.
    """
    try:
        data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    except OSError as exc:
        log.warning("Could not read analyzer config %s: %s", config_path, exc)
        return []
    except yaml.YAMLError as exc:
        log.warning("Malformed analyzer config %s: %s", config_path, exc)
        return []

    analyzers: Sequence[dict] = data.get("analyzers") or []
    runtime_env_dict: dict[str, object] = dict(runtime_env or {})
    outcomes: list[dict] = []

    for analyzer in analyzers:
        if str(analyzer.get("type", "")).lower() != AGENT_BRIDGE_TYPE:
            continue
        if not analyzer.get("enabled", True):
            continue
        name = analyzer.get("name") or "agent-bridge"
        skill_name = analyzer.get("skill_name")
        if not skill_name:
            outcome = _build_outcome(
                analyzer=analyzer,
                output_dir=output_dir,
                status="failed",
                messages=[
                    _message(
                        level="warning",
                        code="missing_skill_name",
                        text="agent-bridge analyzer has no skill_name",
                    ),
                ],
            )
            outcomes.append(outcome)
            log.warning(
                "Analyzer '%s' has type=agent-bridge but no skill_name; skipping.",
                name,
            )
            continue

        result_filename = analyzer.get("result_file") or f"{name}_result.json"
        ai_response = _ai_response_artifact(analyzer, str(result_filename)) or {}
        ai_response_filename = ai_response.get("path") or _derive_ai_response_filename(str(result_filename))
        runtime_filename = _runtime_filename_for(str(name))

        try:
            _write_runtime_file(
                output_dir=output_dir,
                runtime_filename=runtime_filename,
                runtime_env=runtime_env_dict,
            )
        except OSError as exc:
            log.warning(
                "Could not write runtime sidecar for %s: %s; skipping invocation.",
                name, exc,
            )
            outcomes.append(
                _build_outcome(
                    analyzer=analyzer,
                    output_dir=output_dir,
                    status="failed",
                    messages=[_message(level="warning", code="runtime_write_failed", text=exc)],
                ),
            )
            continue

        extra_args = _format_extra_args({
            "output_path": output_dir,
            "result_filename": str(result_filename),
            "ai_response_filename": str(ai_response_filename),
            "runtime_filename": runtime_filename,
        })

        # Optional per-analyzer model override. Each agent-bridge entry in
        # analyzers.yaml may set ``model: <alias-or-id>`` (e.g. ``opus``) to
        # run that skill on a specific Claude model; empty/absent lets the
        # bridge apply its own default (CLAUDE_BRIDGE_MODEL or the CLI default).
        model = str(analyzer.get("model") or "")

        try:
            response = bridge_client.analyze_sync(
                skill_name=str(skill_name),
                project_id=pipeline_id,
                source_path=project_path,
                extra_args=extra_args,
                model=model,
            )
            if response.get("status") != "success":
                outcomes.append(
                    _build_outcome(
                        analyzer=analyzer,
                        output_dir=output_dir,
                        status="failed",
                        messages=[
                            _message(
                                level="warning",
                                code="bridge_error",
                                text=response.get("detail") or response,
                            ),
                        ],
                    ),
                )
                continue
            outcomes.append(
                _build_outcome(
                    analyzer=analyzer,
                    output_dir=output_dir,
                    status="success",
                ),
            )
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            log.warning("Error during agent-bridge launch of %s : %s.", name, exc)
            outcomes.append(
                _build_outcome(
                    analyzer=analyzer,
                    output_dir=output_dir,
                    status="failed",
                    messages=[_message(level="warning", code="bridge_exception", text=exc)],
                ),
            )

    return outcomes
