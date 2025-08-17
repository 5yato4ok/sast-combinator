"""
Shared utilities for interacting with Docker within the SAST pipeline.

This module centralises common Docker operations such as checking if
images exist and running containers. By using these helpers from both
``analyzer_runner.py`` and ``project_builder.py``, we avoid code
duplication and ensure consistent logging and output handling across
different parts of the pipeline.
"""

from __future__ import annotations

import subprocess
import os
import re
import uuid
import selectors
import logging
from typing import Dict, Optional, Iterable

log = logging.getLogger(__name__)

def get_pipeline_id() -> str:
    pipeline_id = os.environ.get("PIPELINE_ID", None)
    if pipeline_id is None:
        pipeline_id = uuid.uuid4().hex[:8]
        os.environ["PIPELINE_ID"] = pipeline_id
    return pipeline_id

def construct_container_name(image: str):
    pipeline_id = get_pipeline_id()

    # Construct container name with pipeline ID if available
    uid = uuid.uuid4().hex[:8]
    return f"sast_{pipeline_id}_{image}_{uid}", pipeline_id

def image_exists(image_name: str) -> bool:
    """Check whether a Docker image is present locally.

    A small wrapper around ``docker images -q``. Returns True if the
    image has been built/pulled already, or False otherwise.
    """
    result = subprocess.run(
        ["docker", "images", "-q", image_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.stdout.strip() != ""


_LEVEL_TOKEN_RE = re.compile(r'\[(DEBUG|INFO|WARNING|WARN|ERROR|ERR|CRITICAL|CRIT)\]', re.IGNORECASE)

def _log_container_line(line: str, stream: str = "stdout", log_addition:str = "") -> None:
    text = line.rstrip("\r\n")

    last = None
    for last in _LEVEL_TOKEN_RE.finditer(text):
        pass

    if last:
        level = last.group(1).upper()
        msg = log_addition + text[last.end():].lstrip()

        if level in ("WARN", "WARNING"):
            log.warning(msg); return
        if level in ("ERR", "ERROR"):
            log.error(msg); return
        if level in ("CRIT", "CRITICAL"):
            log.critical(msg); return
        if level == "DEBUG":
            log.debug(msg); return
        # INFO by default
        log.info(msg); return

    # fallback: if there is no [LEVEL] — stderr -> WARNING, stdout -> INFO
    if stream == "stderr":
        log.warning(log_addition + text)
    else:
        log.info(log_addition + text)

def run_logged_cmd(cmd, log_addition=None):
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    ) as proc:
        assert proc.stdout is not None and proc.stderr is not None
        sel = selectors.DefaultSelector()
        # Register both stdout and stderr file descriptors
        sel.register(proc.stdout, selectors.EVENT_READ, data=("stdout", proc.stdout))
        sel.register(proc.stderr, selectors.EVENT_READ, data=("stderr", proc.stderr))
        while True:
            events = sel.select()
            if not events:
                break
            for key, _ in events:
                stream_name, fileobj = key.data
                line = fileobj.readline()
                if line:
                    _log_container_line(line.rstrip("\n"), stream=stream_name)
                else:
                    # EOF reached on this stream
                    sel.unregister(fileobj)
                    fileobj.close()
            # If both stdout and stderr have been closed, we're done
            if not sel.get_map():
                break
        returncode = proc.wait()
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, cmd)
        return None

def delete_image_if_exist(image_name):
    if not image_exists(image_name):
        return

    run_logged_cmd(["docker", "image", "rm", image_name])


def run_container(
    *,
    image: str,
    name: Optional[str] = None,
    volumes_from: Optional[str] = None,
    volumes: Optional[Dict[str, str]] = None,
    env: Optional[Dict[str, str]] = None,
    args: Optional[Iterable[str]] = None,
    check: bool = True,
) -> subprocess.CompletedProcess | None:
    """Run a Docker container with optional volume and environment configuration.

    This helper builds a ``docker run`` command using a few high-level
    parameters and either streams the output to the Python logger in
    real time or returns a completed process with captured output.

    :param image: Name of the image to run.
    :param name: Optional name to assign to the container (``--name``).
    :param volumes_from: Name of an existing container whose volumes should be
        mounted into this container (``--volumes-from``). Typically used when
        analyzers share a builder container's filesystem.
    :param volumes: Mapping of host paths to container mount points
        (``-v host:container``).
    :param env: Mapping of environment variables to export into the container.
    :param args: Additional positional arguments to pass to the container after the image name.
    :param check: If True, a non-zero exit code raises ``CalledProcessError``.
    """
    cmd: list[str] = ["docker", "run", "--rm"]
    # Always assign a container name to allow for clean termination on interrupt.
    # If a name was not provided, generate a unique one using a UUID.  This
    # helps us reference the container when sending kill commands.
    container_name = name
    # Determine a pipeline ID from the environment (if set) to tag all containers
    pipeline_id = os.environ.get("PIPELINE_ID",None)
    if container_name is None:
        container_name, pipeline_id = construct_container_name(image)
    elif pipeline_id and pipeline_id not in name:
        raise Exception("Incorrect container name, lack of PIPELINE_ID")

    cmd += ["--name", container_name]
    if volumes_from:
        cmd += ["--volumes-from", volumes_from]
    if volumes:
        for host_path, container_path in volumes.items():
            cmd += ["-v", f"{host_path}:{container_path}"]
    if env:
        for k, v in env.items():
            cmd += ["-e", f"{k}={v}"]
    # Append image and any additional arguments
    cmd += [image]
    if args:
        cmd += list(args)

    run_logged_cmd(cmd, f"[{image}]")

def build_image(
    *,
    image_name: str,
    context_dir: str,
    dockerfile: Optional[str] = None,
    build_args: Optional[Dict[str, str]] = None,
    check: bool = True
) -> None:
    """Build a Docker image with optional build arguments and logging.

    This helper constructs a ``docker build`` command and either streams
    the build output to the logger or captures it.  Lines containing
    ``error``, ``Error`` or ``failed`` are logged as errors; all other
    lines are logged at INFO level.

    :param image_name: Tag/name to assign to the built image.
    :param context_dir: Path to the build context (the directory containing the Dockerfile).
    :param dockerfile: Optional path to a Dockerfile. If provided, passed via ``-f``.
    :param build_args: Mapping of build argument names to values (passed via ``--build-arg``).
    :param check: If True, raise ``CalledProcessError`` for non-zero exit codes.
    """
    cmd: list[str] = ["docker", "build"]
    # Append build-arg flags
    if build_args:
        for k, v in build_args.items():
            cmd += ["--build-arg", f"{k}={v}"]
    # Tag name
    cmd += ["-t", image_name]
    # Custom Dockerfile if provided
    if dockerfile:
        cmd += ["-f", dockerfile]
    # Context directory
    cmd += ["."]

    # Function to log each build line
    def log_build_line(line: str) -> None:
        if not line:
            return
        txt = line.strip()
        lower = txt.lower()
        if "error" in lower or "failed" in lower:
            log.error(f"[build {image_name}]{txt}")
        else:
            log.info(f"[build {image_name}]{txt}")

    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=context_dir,
        bufsize=1,
    ) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            log_build_line(line)
        returncode = proc.wait()
        if check and returncode != 0:
            raise subprocess.CalledProcessError(returncode, cmd)

def cleanup_pipeline_containers(pipeline_id: str) -> None:
    """Remove all Docker containers associated with the given pipeline ID.

    Containers launched by :func:`run_container` include the pipeline ID in
    their names (``sast_<pipeline_id>_...``).  This helper lists all such
    containers—both running and stopped—and forcibly removes them.  It is
    intended to be called by host-level code when a pipeline is aborted or
    interrupted to ensure no orphaned containers continue running.

    :param pipeline_id: The identifier of the pipeline whose containers
        should be cleaned up.  If empty or None, the function does nothing.
    """
    if not pipeline_id:
        return
    try:
        # List all containers (running or exited) whose names start with the pipeline prefix
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name=sast_{pipeline_id}",
                "--format",
                "{{.Names}}",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not names:
            return
        for name in names:
            try:
                run_logged_cmd(["docker", "rm", "-f", name])
                log.info("Removed pipeline container %s", name)
            except Exception as exc:
                log.warning("Failed to remove container %s: %s", name, exc)
    except Exception as exc:
        log.warning("Failed to clean up pipeline containers for %s: %s", pipeline_id, exc)