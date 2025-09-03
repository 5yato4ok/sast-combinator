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

import os
import shutil
import logging
from pathlib import Path
from . import docker_utils
import json
from datetime import datetime


log = logging.getLogger(__name__)


def configure_project_run_analyses(
        script_path: str,
        output_dir: str,
        languages,
        analyzer_config,
        dockerfile_path: str,
        context_dir: str,
        image_name: str = "project-builder",
        project_path: str = "/tmp/my_project",
        force_rebuild: bool = False,
        rebuild_images: bool = False,
        version: str | None = None,
        log_level: str | None = None,
        min_time_class: str = "",
        analyzers=None,
):
    """Build the builder image and run all configured analyzers.

    :param script_path: Path to the project configuration script on the host.
    :param output_dir: Directory on the host where analysis results will be written.
    :param image_name: Name of the Docker image for the builder container.
    :param dockerfile_path: Path to the builder Dockerfile.
    :param project_path: Directory in the container where the project will be mounted.
    :param force_rebuild: If True, force a rebuild of the project.
    :param version: Optional commit or branch name to checkout.
    :return: Path to the output directory with a timestamp appended.
    """

    if analyzers is None:
        analyzers = []

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"{output_dir}/{timestamp}"
    os.makedirs(output_dir, exist_ok=True)

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

    if not os.path.exists(project_path):
        os.makedirs(project_path)

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
        default_log_level="DEBUG"
    )

    # Clean up the copied script
    try:
        target_path.unlink()
        if not any(target_dir.iterdir()):
            target_dir.rmdir()
    except Exception as e:
        log.warning("Failed to delete copied file: %s", e)

    builder_container_name, pipeline_id = docker_utils.construct_container_name(image_name)

    # Build environment variables dictionary for the builder container
    env_dict: dict[str, str] = {
        "FORCE_REBUILD": "1" if force_rebuild else "0",
        "BUILDER_CONTAINER": builder_container_name,
    }
    # Propagate logging level and version if provided
    if log_level:
        env_dict["LOG_LEVEL"] = log_level
    if version is not None:
        env_dict["PROJECT_VERSION"] = str(version)

    tmp_analyzer_config_path = analyzer_config.prepare_pipeline_analyzer_config(languages, min_time_class, analyzers)
    env_dict["PIPELINE_ID"] = pipeline_id
    # Construct volume mapping for the builder container
    volumes = {
        os.path.abspath(project_path): "/workspace",
        os.path.abspath(output_dir): "/shared/output",
        "/var/run/docker.sock": "/var/run/docker.sock",
        tmp_analyzer_config_path : "/app/analyzers.yaml"
    }

    log.info(f"Running builder container {builder_container_name}")
    try:
        docker_utils.run_container(
            image=image_name,
            name=builder_container_name,
            volumes=volumes,
            env=env_dict,
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
    if os.path.exists(path_to_launch_description):
        with open(path_to_launch_description, 'r', encoding="utf-8") as f:
            launch_data = json.load(f)
            launch_data["is_correct"] = True
    else:
        launch_data = dict()
        launch_data["is_correct"] = False

    print(project_path)
    def replace_in_dict(obj, target_path):
        if isinstance(obj, dict):
            return {k: replace_in_dict(v, target_path) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [replace_in_dict(i, target_path) for i in obj]
        elif isinstance(obj, str):
            return obj.replace("/workspace/", f"{target_path}/") #TODO: remove build-tmp everywhere
        else:
            return obj

    trim_path = launch_data.get("project_path", None)
    launch_data = replace_in_dict(launch_data, project_path)
    launch_data["trim_path"] = trim_path
    launch_data["output_dir"] = output_dir
    launch_data["tmp_analyzer_config_path"] = tmp_analyzer_config_path

    return launch_data