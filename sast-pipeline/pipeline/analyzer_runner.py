"""
Functions for discovering, building and running analyzers defined in
analyzer config.

This version uses the standard ``logging`` module instead of printing
directly to stdout.  The caller (typically ``run_pipeline.py``) should
configure the logging level and handlers.  Messages emitted here will
respect that configuration.  In addition, the Dockerfile path for each
analyzer can be overridden via an optional ``dockerfile_path`` field in
the YAML configuration; if not provided, it defaults to ``Dockerfiles/<name>``.

Environment variables required by analyzers (e.g. tokens) are read
before container launch.  If they are missing, an exception is raised.
"""

from __future__ import annotations

import json
import logging
import os

import yaml  # type: ignore

from . import config_utils
from . import docker_utils


log = logging.getLogger(__name__)
AGENT_BRIDGE_TYPE = "agent-bridge"


def _message(*, level: str, code: str, text: object) -> dict[str, str]:
    return {"level": level, "code": code, "text": str(text or "")[:2000]}


def _build_outcome(*, analyzer: dict, output_dir: str, status: str, messages: list[dict] | None = None) -> dict:
    name = str(analyzer.get("name") or "unknown")
    result_file = config_utils.AnalyzersConfigHelper.get_analyzer_result_file_name(analyzer)
    result_exists = os.path.exists(os.path.join(output_dir, result_file))
    required_result = bool(analyzer.get("required_result", False))
    outcome_messages = list(messages or [])
    if status == "success" and required_result and not result_exists:
        status = "missing_result"
        outcome_messages.append(
            _message(
                level="warning",
                code="missing_result",
                text=f"Required analyzer result file was not produced: {result_file}",
            ),
        )
    return {
        "name": name,
        "type": str(analyzer.get("type", "default")).lower(),
        "status": status,
        "degraded": status in {"failed", "missing_result"} and required_result,
        "required_result": required_result,
        "result_file": result_file,
        "result_exists": result_exists,
        "messages": outcome_messages,
        "artifacts": analyzer.get("artifacts") or {},
    }


def run_docker(
    image: str,
    builder_container: str,
    args: list[str],
    project_path: str,
    output_dir: str,
    pipeline_id: str,
    env_vars: list[str] | None = None,
    dockerfile_dir: str = "",
) -> None:
    """Run a single analyzer container.

    :param image: Name of the analyzer image to run.
    :param builder_container: Name of the builder container whose volumes
                              will be mounted into this analyzer.
    :param args: Additional positional arguments to pass to the analyzer.
    :param project_path: Path of the project on the host (unused but kept for API compatibility).
    :param output_dir: Output directory on the host (unused but kept for API compatibility).
    :param env_vars: List of environment variable names to expose to the analyzer.
    :raises Exception: If a required environment variable is not set.
    """
    log.info("Running analyzer image '%s'", image)
    # Build environment variables dictionary
    env: dict[str, str] = {}
    if env_vars:
        for var in env_vars:
            if var in os.environ:
                env[var] = os.environ[var]
            else:
                raise Exception(f"Required environment variable '{var}' is not set.")
    volumes = (
        None
        if builder_container
        else {
            os.path.abspath(project_path): "/workspace",
            os.path.abspath(output_dir): "/shared/output",
        }
    )
    # One entry point for every containerized step: it ensures the image, builds a name dockerd
    # accepts, and refuses a mount source the daemon cannot read.
    docker_utils.run_pipeline_container(
        image=image,
        dockerfile_dir=dockerfile_dir,
        pipeline_id=pipeline_id,
        volumes_from=builder_container or None,
        volumes=volumes,
        env=env or None,
        args=args,
    )


def env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in {"1", "true", "yes", "y", "on"}:
        return True
    if val in {"0", "false", "no", "n", "off"}:
        return False

    return default


def run_selected_analyzers(
    config_path: str,
    pipeline_id: str,
    analyzers_to_run: list[str] | None = None,
    project_path: str = "./my_project",
    output_dir: str = "/tmp/sast_output",
    builder_container: str = "builder-env",
    log_level: str | None = None,
    max_time_class: str | None = None,
) -> None:
    """Load analyzer definitions and run the selected ones.

    :param config_path: Path to the analyzers YAML file.
    :param analyzers_to_run: Optional list of analyzer names to run. If
                             omitted, all enabled analyzers are run.
    :param project_path: Path to the project source on the host.
    :param output_dir: Directory on the host where analyzer results will be written.
    :param builder_container: Name of the builder container. Its volumes
                              will be mounted into each analyzer.
    """
    os.makedirs(output_dir, exist_ok=True)
    config_helper = config_utils.AnalyzersConfigHelper(config_path)
    analyzers = config_helper.get_filtered_analyzers(analyzers_to_run, max_time_class=max_time_class,
                                                     non_compile_project=env_flag("NON_COMPILE_PROJECT", True))

    log.debug(f"Analyzers to launch: {analyzers}")

    if len(analyzers) == 0:
        log.warning("No analyzers to launch")
        return None
    # Sort by time_class for predictable ordering
    analyzers.sort(key=lambda a: config_helper.ANALYZER_ORDER.get(a.get("time_class", "medium"), 1))
    analyzers_names = [str(a.get("name")) for a in analyzers]
    log.info(
        "Selected analyzers: %s",
        ", ".join(analyzers_names),
    )
    launch_info = dict()
    launch_info["project_path"] = project_path
    launch_info["launched_analyzers"] = analyzers_names
    launch_info["git"] = docker_utils.collect_git_metadata(project_path)

    analyzer_outcomes = []

    for analyzer in analyzers:
        name = analyzer.get("name")
        analyzer_type = str(analyzer.get("type", "")).lower()

        # Agent analyzers run on the host orchestrator because their bridge
        # socket is not available inside the builder container.
        if analyzer_type == AGENT_BRIDGE_TYPE:
            log.info(
                "Skipping agent-bridge analyzer '%s' inside builder; "
                "the host orchestrator runs it via the bridge.",
                name,
            )
            continue

        image = analyzer.get("image")
        # Ensuring the image is part of running a step, so it happens inside run_docker rather
        # than here: one place decides what must be true before `docker run`.
        dockerfile_dir = str(analyzer.get("dockerfile_path", f"Dockerfiles/{name}"))
        input_path = analyzer.get("input", project_path)
        output_file_name = config_helper.get_analyzer_result_file_name(analyzer)

        args = [str(input_path), str(output_dir), str(output_file_name)]
        env_vars = analyzer.get("env", []) or []
        if log_level:
            env_vars += ["LOG_LEVEL"]
        try:
            run_docker(
                str(image),
                builder_container,
                args,
                project_path,
                output_dir,
                pipeline_id,
                env_vars,
                dockerfile_dir=dockerfile_dir,
            )
            analyzer_outcomes.append(_build_outcome(analyzer=analyzer, output_dir=output_dir, status="success"))
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            log.warning(f"Error occurred during launching of {name} : {exc}.")
            analyzer_outcomes.append(
                _build_outcome(
                    analyzer=analyzer,
                    output_dir=output_dir,
                    status="failed",
                    messages=[_message(level="warning", code="runner_exception", text=exc)],
                ),
            )

    launch_info["analyzer_outcomes"] = analyzer_outcomes
    with open(os.path.join(output_dir, "launch_description.json"), "w", encoding="utf-8") as f:
        json.dump(launch_info, f, indent=4, ensure_ascii=False)

    log.info("All selected analyzers completed.")
