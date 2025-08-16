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
import logging
from typing import Dict, Optional, Iterable

log = logging.getLogger(__name__)

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


def _log_container_line(line: str, stream: str = "stdout") -> None:
    """
    Emit a single line from container output to the appropriate logging level.

    Log level is chosen based on simple heuristics:
      * Lines starting with ``[x]`` are logged as errors.
      * Lines starting with ``[!]`` are logged as warnings.
      * Lines starting with ``[+]``, ``[✓]`` or ``[=]`` are logged as info.
      * Unknown prefixes on stderr become warnings; on stdout become debug.

    :param line: The raw line of output.
    :param stream: Either ``stdout`` or ``stderr`` to indicate the source.
    """
    if not line:
        return
    text = line.strip()
    if len(text) == 0:
        return
    if text.startswith("[x]"):
        level_func = log.error
    elif text.startswith("[!]"):
        level_func = log.warning
    elif text.startswith("[+]") or text.startswith("[✓]") or text.startswith("[=]"):
        level_func = log.info
    else:
        level_func = log.warning if stream == "stderr" else log.debug
    level_func(text)


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
    if name:
        cmd += ["--name", name]
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

    # Stream stdout/stderr to the logger while the container runs
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    ) as proc:
        assert proc.stdout is not None and proc.stderr is not None
        for line in proc.stdout:
            _log_container_line(line.rstrip(), stream="stdout")
        for line in proc.stderr:
            _log_container_line(line.rstrip(), stream="stderr")
        returncode = proc.wait()
        if check and returncode != 0:
            raise subprocess.CalledProcessError(returncode, cmd)
        return None


def build_image(
    *,
    image_name: str,
    context_dir: str,
    dockerfile: Optional[str] = None,
    build_args: Optional[Dict[str, str]] = None,
    check: bool = True,
    workdir: Optional[str] = None,
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
    cmd += [context_dir]

    # Determine working directory: when dockerfile is relative path outside context,
    # we need to set cwd accordingly. For simplicity, use the directory part of context_dir.
    # The caller is responsible for passing appropriate context_dir and dockerfile.
    # Use the provided working directory, if any.  If workdir is None, the
    # current working directory will be used.  When context_dir and
    # dockerfile are relative paths, callers should set workdir to the
    # directory from which those paths make sense.
    cwd = workdir

    # Function to log each build line
    def log_build_line(line: str) -> None:
        if not line:
            return
        txt = line.strip()
        lower = txt.lower()
        if "error" in lower or "failed" in lower:
            log.error(txt)
        else:
            log.info(txt)

    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=cwd,
        bufsize=1,
    ) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            log_build_line(line)
        returncode = proc.wait()
        if check and returncode != 0:
            raise subprocess.CalledProcessError(returncode, cmd)