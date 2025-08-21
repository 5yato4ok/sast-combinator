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

import subprocess
import yaml  # type: ignore
import os
import logging
from pathlib import Path
import docker_utils
import config_utils


log = logging.getLogger(__name__)

def build_image_if_needed(image_name: str, dockerfile_dir: str) -> None:
    """Ensure that a Docker image exists for the given analyzer.

    If the image already exists, a debug message is logged and the build
    is skipped.  Otherwise, the image is built using the specified
    Dockerfile directory.  The ``LOG_LEVEL`` environment variable is
    passed as a build argument so that ``apt-get`` commands in the
    Dockerfile can adjust their verbosity.
    """
    if docker_utils.image_exists(image_name):
        log.debug("Image '%s' already exists; skipping build", image_name)
        return
    log.info("Building image '%s'…", image_name)
    # Propagate LOG_LEVEL into the build stage if set
    build_args: dict[str, str] = {}
    log_level_env = os.environ.get("LOG_LEVEL")
    if log_level_env:
        build_args["LOG_LEVEL"] = log_level_env
    # Use the shared helper to perform the build with logging
    docker_utils.build_image(
        image_name=image_name,
        context_dir=dockerfile_dir,
        dockerfile=None,
        build_args=build_args or None,
        check=True
    )


def run_docker(
    image: str,
    builder_container: str,
    args: list[str],
    project_path: str,
    output_dir: str,
    env_vars: list[str] | None = None,
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
    if builder_container:
        # Delegate to the shared docker_utils helper for running containers
        docker_utils.run_container(
            image=image,
            volumes_from=builder_container,
            env=env or None,
            args=args,
        )
    else:
        volumes = {
            os.path.abspath(project_path): "/workspace",
            os.path.abspath(output_dir): "/shared/output",
        }
        docker_utils.run_container(
            image=image,
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
    analyzers_to_run: list[str] | None = None,
    exclude_slow: bool = False,
    project_path: str = "./my_project",
    output_dir: str = "/tmp/sast_output",
    builder_container: str = "builder-env",
    log_level: str | None = None
) -> None:
    """Load analyzer definitions and run the selected ones.

    :param config_path: Path to the analyzers YAML file.
    :param analyzers_to_run: Optional list of analyzer names to run. If
                             omitted, all enabled analyzers are run.
    :param exclude_slow: If true, analyzers marked as ``time_class: slow``
                         are skipped.
    :param project_path: Path to the project source on the host.
    :param output_dir: Directory on the host where analyzer results will be written.
    :param builder_container: Name of the builder container. Its volumes
                              will be mounted into each analyzer.
    """
    os.makedirs(output_dir, exist_ok=True)
    config_helper = config_utils.AnalyzersConfigHelper(config_path)

    analyzers = config_helper.get_analyzers()
    log.info(f" Analyzers: {analyzers}")
    # Filter analyzers by requested names or enabled flag
    if analyzers_to_run:
        analyzers = [a for a in analyzers if a.get("name") in analyzers_to_run and a.get("enabled", True)]
    else:
        analyzers = [a for a in analyzers if a.get("enabled", True)]

    if not analyzers:
        log.warning("No analyzers to launch")
        return None

    # Sort by time_class for predictable ordering
    analyzers.sort(key=lambda a: config_helper.ANALYZER_ORDER.get(a.get("time_class", "medium"), 1))
    log.info(
        "Selected analyzers: %s",
        ", ".join([str(a.get("name")) for a in analyzers]),
    )

    for analyzer in analyzers:
        name = analyzer.get("name")
        image = analyzer.get("image")
        time_class = analyzer.get("time_class", "medium")
        type = analyzer.get("type", "default")
        if type == "builder" and env_flag("NON_COMPILE_PROJECT", True):
            log.warning(f"Attempt to launch analyzer {name} on non compile project. Skipping...")
            continue

        dockerfile_path = str(analyzer.get("dockerfile_path", f"/app/Dockerfiles/{name}"))

        if exclude_slow and time_class == "slow":
            log.info("Skipping slow analyzer '%s'", name)
            continue
        build_image_if_needed(str(image), dockerfile_path)
        input_path = analyzer.get("input", project_path)
        output_file_name = config_helper.get_analyzer_result_file_name(analyzer)
        args = [str(input_path), str(output_dir), str(output_file_name)]
        env_vars = analyzer.get("env", []) or []
        if log_level:
            env_vars += ["LOG_LEVEL"]
        run_docker(str(image), builder_container, args, project_path, output_dir, env_vars)

    log.info("All selected analyzers completed.")