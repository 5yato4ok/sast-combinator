"""
Utility functions for building a project environment and executing
analyzers.

This version integrates Python's logging module to emit informative
messages instead of printing directly to stdout.  Logging enables
better control over output verbosity (via the root logger configured in
``run_pipeline.py``) and facilitates redirection to files or other
handlers without changing this module.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from . import agent_bridge_runner
from . import docker_utils

log = logging.getLogger(__name__)


def prepare_run_output_dir(output_dir: str | Path) -> Path:
    """Create the timestamped directory shared by every pipeline result producer."""
    run_output_dir = Path(output_dir) / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_output_dir.mkdir(exist_ok=True, parents=True)
    return run_output_dir


def configure_project_run_analyses(
        script_path: str,
        output_dir: str,
        languages,
        analyzer_config,
        dockerfile_path: str,
        context_dir: str,
        pipeline_id: str,
        image_name: str = "project-builder",
        project_path: str = "/tmp/my_project",
        force_rebuild: bool = False,
        rebuild_images: bool = False,
        version: dict | None = None,
        log_level: str | None = None,
        min_time_class: str = "",
        analyzers=None,
        additional_env=None,
        network: str | None = None,
        bridge_client=None,
        agent_bridge_runtime_env=None,
):
    """
    Build the builder image and run all configured analyzers.

    :param script_path: Path to the project configuration script on the host.
    :param output_dir: Directory on the host where analysis results will be written.
    :param image_name: Name of the Docker image for the builder container.
    :param dockerfile_path: Path to the builder Dockerfile.
    :param project_path: Directory in the container where the project will be mounted.
    :param force_rebuild: If True, force a rebuild of the project.
    :param version: Optional dictionary with version information.
    :return: Path to the output directory with a timestamp appended.
    """
    if analyzers is None:
        analyzers = []

    output_dir = str(prepare_run_output_dir(output_dir))

    log.info("Building builder image: %s", image_name)

    if rebuild_images:
        for image in analyzer_config.get_all_images():
            docker_utils.delete_image_if_exist(image)
        docker_utils.delete_image_if_exist(image_name)

    input_path = Path(script_path).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    context_path = Path(context_dir).resolve()
    target_dir = context_path / "tmp"
    target_dir.mkdir(parents=True, exist_ok=True)

    if not Path(project_path).exists():
        Path(project_path).mkdir(parents=True, exist_ok=True)

    # Copy the script into the build context
    target_path = target_dir / input_path.name
    shutil.copy2(input_path, target_path)

    relative_config_path = target_path.relative_to(context_path)

    # Build the builder image with the project config script as a build arg
    build_args = {"PROJECT_CONFIG_PATH": str(relative_config_path)}
    docker_utils.build_image(
        image_name=image_name,
        context_dir=context_dir,
        dockerfile=dockerfile_path,
        build_args=build_args,
        check=True,
        default_log_level="DEBUG",
    )

    # Clean up the copied script
    try:
        target_path.unlink()
        if not any(target_dir.iterdir()):
            target_dir.rmdir()
    except Exception as e:
        log.warning("Failed to delete copied file: %s", e)

    builder_container_name = docker_utils.construct_container_name(image_name, pipeline_id)

    # Build environment variables dictionary for the builder container
    env_dict: dict[str, str] = {
        "FORCE_REBUILD": "1" if force_rebuild else "0",
        "BUILDER_CONTAINER": builder_container_name,
    } | (additional_env or {})
    # Propagate logging level and version if provided
    if log_level:
        env_dict["LOG_LEVEL"] = log_level

    if version and "type" in version:
        log.info("Building builder version: %s", version)
        if version.get("type") in {"GIT_HASH", "GIT_BRANCH"}:
            log.info("Project version %s", version.get("type"))
            env_dict["PROJECT_VERSION"] = (version.get("version") or "master").strip()
        elif version.get("type") == "FILE_HASH":
            # copy sources to project_path
            extracted_sources = version.get("extracted_root")
            if not Path(extracted_sources).exists():
                raise ValueError(f"Path to extracted sources not exists {extracted_sources}")

            if Path(project_path).exists():
                log.info("Removing existing project directory: %s", project_path)
                shutil.rmtree(project_path)
            log.info(f"Copying folder {extracted_sources} to {project_path}")
            subprocess.run(["cp", "-r", extracted_sources, project_path], check=True)
        else:
            raise ValueError(f"Unknown version of type {version['type']}")

    env_dict["PIPELINE_ID"] = pipeline_id

    tmp_analyzer_config_path = analyzer_config.prepare_pipeline_analyzer_config(languages=languages, max_time_class=min_time_class, target_analyzers=analyzers, pipeline_id=pipeline_id)
    # Construct volume mapping for the builder container
    log.debug(f"Path to tmp_analyzer: {tmp_analyzer_config_path}")
    if Path("tmp_analyzer_config_path").exists():
        log.debug("TMP analyzer path exist")
    else:
        log.debug("Tmp analyzer path doesn't exist")

    volumes = {
        os.path.abspath(project_path): "/workspace",
        os.path.abspath(output_dir): "/shared/output",
        "/var/run/docker.sock": "/var/run/docker.sock",
        tmp_analyzer_config_path: "/app/analyzers.yaml",
    }

    log.info(f"Running builder container {builder_container_name}")
    try:
        # Not run_pipeline_container: the builder image is rebuilt every run with per-project
        # build args above (not "build if absent"), and the Docker socket it mounts is not step
        # data, so it cannot satisfy that helper's shared-root rule.
        docker_utils.run_container(
            image=image_name,
            name=builder_container_name,
            volumes=volumes,
            env=env_dict,
            pipeline_id=pipeline_id,
            network=network,
        )
    except KeyboardInterrupt:
        # Ensure that all containers associated with this pipeline are terminated
        log.warning("Pipeline interrupted; cleaning up spawned containers…")
        try:
            docker_utils.cleanup_pipeline_containers(pipeline_id)
        except Exception as exc:
            log.warning("Failed to clean up pipeline containers: %s", exc)
        raise

    log.info("Builder and analysis finished. Results saved in %s", output_dir)

    path_to_launch_description = os.path.join(output_dir, "launch_description.json")
    if Path(path_to_launch_description).exists():
        with Path(path_to_launch_description).open(encoding="utf-8") as f:
            launch_data = json.load(f)
            launch_data["is_correct"] = True
    else:
        launch_data = dict()
        launch_data["is_correct"] = False

    log.debug(f"Project path: {project_path}. Path to launch description: {path_to_launch_description}")

    def replace_in_dict(obj, target_path):
        if isinstance(obj, dict):
            return {k: replace_in_dict(v, target_path) for k, v in obj.items()}
        if isinstance(obj, list):
            return [replace_in_dict(i, target_path) for i in obj]
        if isinstance(obj, str):
            return obj.replace("/workspace/", f"{target_path}/")  # TODO: remove build-tmp everywhere
        return obj

    trim_path = launch_data.get("project_path")
    launch_data = replace_in_dict(launch_data, project_path)

    # After replace_in_dict, launch_data["project_path"] contains the resolved host path
    # to the actual source root (e.g. /tmp/aist/.../runs/abc123/dev_myapp). Use it
    # as source_path for agent-bridge analyzers so findings carry correct relative paths.
    agent_source_root = launch_data.get("project_path") or project_path

    agent_outcomes: list[dict] = []

    # agent-bridge analyzers were skipped inside the builder container because
    # the aist-triage-bridge UDS lives on this host. Run them now so their
    # result files land in `output_dir` before upload_results_internal reads it.
    # The caller (AIST or any other host) must pass a constructed bridge_client;
    # without one we silently skip the phase so standalone sast-pipeline runs
    # (without AIST) keep working.
    if bridge_client is not None:
        agent_outcomes = agent_bridge_runner.run_agent_bridge_analyzers(
            bridge_client=bridge_client,
            config_path=tmp_analyzer_config_path,
            pipeline_id=pipeline_id,
            project_path=agent_source_root,
            output_dir=output_dir,
            runtime_env=agent_bridge_runtime_env or {},
        )

    existing_outcomes = launch_data.get("analyzer_outcomes") or []
    launch_data["analyzer_outcomes"] = [*existing_outcomes, *agent_outcomes]
    launch_data["trim_path"] = trim_path
    launch_data["output_dir"] = output_dir
    launch_data["tmp_analyzer_config_path"] = tmp_analyzer_config_path

    with Path(path_to_launch_description).open("w", encoding="utf-8") as f:
        json.dump(launch_data, f, indent=4, ensure_ascii=False)

    return launch_data
