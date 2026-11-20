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
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path

from . import agent_bridge_runner, docker_utils
from .build_configuration import BUILDER_RESERVED_ENV, SourceRevision, SourceType
from .build_runtime import prepare_build_runtimes
from .config_utils import AnalyzersConfigHelper
from .run_output import prepare_run_output_dir

# The builder mounts the project at /workspace; an uploaded archive is copied to that root itself,
# so the container path is either exactly /workspace or a path below it.
_CONTAINER_PROJECT_ROOT = re.compile(r"/workspace(?=/|$)")

log = logging.getLogger(__name__)


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
        version: SourceRevision | dict | None = None,
        log_level: str | None = None,
        min_time_class: str = "",
        analyzers=None,
        additional_env=None,
        secret_env=None,
        network: str | None = None,
        bridge_client=None,
        agent_bridge_runtime_env=None,
        base_image: str = "",
):
    """
    Build the builder image and run all configured analyzers.

    :param script_path: Path to the project configuration script on the host.
    :param output_dir: Directory on the host where analysis results will be written.
    :param image_name: Name of the Docker image for the builder container.
    :param dockerfile_path: Path to the builder Dockerfile.
    :param base_image: Optional builder base image reference, supplied by the caller's project configuration.
    :param project_path: Directory in the container where the project will be mounted.
    :param force_rebuild: If True, force a rebuild of the project.
    :param version: Source revision; legacy dictionary callers are normalized at this boundary.
    :param secret_env: Builder-only variables, masked in the relayed output. A name that is
        reserved by the builder or also present in ``additional_env`` raises ``ValueError``.
    :return: Path to the output directory with a timestamp appended.
    """
    if analyzers is None:
        analyzers = []
    secret_env = dict(secret_env or {})
    redefined = sorted(secret_env.keys() & (BUILDER_RESERVED_ENV | (additional_env or {}).keys()))
    if redefined:
        raise ValueError(f"Secret builder environment redefines {', '.join(redefined)}")

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
    if base_image:
        build_args["BUILDER_BASE_IMAGE"] = base_image
    with tempfile.TemporaryDirectory(prefix="sast-builder-") as build_metadata:
        iid_file = Path(build_metadata) / "image-id"
        docker_utils.build_image(
            image_name=image_name,
            context_dir=context_dir,
            dockerfile=dockerfile_path,
            build_args=build_args,
            check=True,
            default_log_level="DEBUG",
            iid_file=str(iid_file),
        )
        builder_image = iid_file.read_text(encoding="utf-8").strip()

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
    for key in ("SAST_ANALYZER_MEMORY", "SAST_ANALYZER_CPUS"):
        if key in os.environ:
            env_dict.setdefault(key, os.environ[key])
    # Propagate logging level and version if provided
    if log_level:
        env_dict["LOG_LEVEL"] = log_level

    if isinstance(version, dict):
        version = SourceRevision.from_dict(version)
    if version and version.type is not None:
        log.info("Building builder version: %s", version)
        if version.type in {SourceType.GIT_HASH, SourceType.GIT_BRANCH}:
            log.info("Project version %s", version.type)
            env_dict["PROJECT_VERSION"] = (version.version or "master").strip()
        elif version.type == SourceType.FILE_HASH:
            # copy sources to project_path
            extracted_sources = version.extracted_root
            if not Path(extracted_sources).exists():
                raise ValueError(f"Path to extracted sources not exists {extracted_sources}")

            if Path(project_path).exists():
                log.info("Removing existing project directory: %s", project_path)
                shutil.rmtree(project_path)
            log.info(f"Copying folder {extracted_sources} to {project_path}")
            subprocess.run(["cp", "-r", extracted_sources, project_path], check=True)
        else:
            raise ValueError(f"Unknown version of type {version.type}")

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

    selected = AnalyzersConfigHelper(tmp_analyzer_config_path).get_filtered_analyzers(
        None, max_time_class="slow", non_compile_project=False,
    )
    resources = docker_utils.ContainerResources.from_env(dict(os.environ) | env_dict, "SAST_BUILDER")
    log.info(f"Running builder container {builder_container_name}")
    try:
        # Not run_pipeline_container: the builder image is rebuilt every run with per-project
        # build args above (not "build if absent"), and the Docker socket it mounts is not step
        # data, so it cannot satisfy that helper's shared-root rule.
        with prepare_build_runtimes(selected, pipeline_id) as runtimes:
            env_dict["SAST_BUILD_RUNTIMES"] = json.dumps([asdict(runtime) for runtime in runtimes])
            for runtime in runtimes:
                volumes.update(runtime.mounts)
            docker_utils.run_container(
                image=builder_image,
                name=builder_container_name,
                volumes=volumes,
                env=env_dict | secret_env,
                pipeline_id=pipeline_id,
                network=network,
                resources=resources,
                redact=secret_env.values(),
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
            return _CONTAINER_PROJECT_ROOT.sub(lambda _: target_path, obj)
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
