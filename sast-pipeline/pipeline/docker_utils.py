"""
Shared utilities for interacting with Docker within the SAST pipeline.

This module centralises common Docker operations such as checking if
images exist and running containers. By using these helpers from both
``analyzer_runner.py`` and ``project_builder.py``, we avoid code
duplication and ensure consistent logging and output handling across
different parts of the pipeline.
"""

from __future__ import annotations

import hashlib
import subprocess
import os
import re
import shutil
import uuid
import selectors
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, Optional, Iterable, Tuple

log = logging.getLogger(__name__)

# Bind-mount sources are resolved by the daemon on the host, so only paths the host and this
# container agree on can be handed to `docker run`. Compose mounts AIST_TMP_DIR at the same
# location on both sides; everything else, including this container's own /tmp, is private.
HOST_SHARED_ROOT = Path(os.environ.get("AIST_TMP_DIR", "/tmp/aist"))


# The root of this package on disk. Catalog entries spell their build context as it appears
# inside the pipeline image, where this root is mounted at /app; a caller running elsewhere --
# the Celery worker, where /app is the platform project -- needs the same entry re-anchored here.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent

# Stamped on every image whose build inputs are files of this package, so a tag that names a
# protocol version instead of a build ("aist-dast-connector:v2") can still be told apart from the
# sources it was built from.
SOURCE_DIGEST_LABEL = "com.aist.source-digest"


class UnsharedWorkspaceError(ValueError):
    """A path was passed to a container that the Docker daemon cannot read."""


class BuildContextNotFoundError(FileNotFoundError):
    """A catalog entry's build context does not exist under any known root."""


def get_pipeline_id() -> str:
    return uuid.uuid4().hex[:8]

_CONTAINER_NAME_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")


def construct_container_name(image: str, pipeline_id: str) -> str:
    """Build a container name dockerd accepts for any image a catalog may declare.

    dockerd only accepts ``[a-zA-Z0-9][a-zA-Z0-9_.-]*``, so every other character in the image
    reference is folded to '_' -- registry separators, and the ':' of a tag. The pipeline id is
    kept verbatim because cleanup_pipeline_containers finds a pipeline's containers by it.
    """
    safe_image = _CONTAINER_NAME_UNSAFE.sub("_", image)
    return f"sast_{safe_image}_{pipeline_id}"

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

def run_logged_cmd(cmd, log_addition=""):
    import codecs

    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        bufsize=0,
    ) as proc:
        assert proc.stdout and proc.stderr

        os.set_blocking(proc.stdout.fileno(), False)
        os.set_blocking(proc.stderr.fileno(), False)

        sel = selectors.DefaultSelector()
        sel.register(proc.stdout, selectors.EVENT_READ, data=("stdout", proc.stdout))
        sel.register(proc.stderr, selectors.EVENT_READ, data=("stderr", proc.stderr))

        decoders = {
            "stdout": codecs.getincrementaldecoder("utf-8")("replace"),
            "stderr": codecs.getincrementaldecoder("utf-8")("replace"),
        }

        try:
            while True:
                events = sel.select(timeout=0.1)
                for key, _ in events:
                    stream_name, fileobj = key.data
                    chunk = fileobj.read()
                    if chunk:
                        text = decoders[stream_name].decode(chunk)
                        for line in text.splitlines():
                            _log_container_line(line, stream=stream_name, log_addition=log_addition)
                    else:
                        sel.unregister(fileobj)

                if proc.poll() is not None and not sel.get_map():
                    break

            returncode = proc.wait()
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, cmd)
        finally:
            for key in list(sel.get_map().values()):
                try:
                    sel.unregister(key.fileobj)
                except Exception:
                    pass
            sel.close()

def delete_image_if_exist(image_name):
    if not image_exists(image_name):
        return

    run_logged_cmd(["docker", "image", "rm", image_name])


def run_container(
    *,
    image: str,
    pipeline_id: str,
    name: Optional[str] = None,
    volumes_from: Optional[str] = None,
    volumes: Optional[Dict[str, str]] = None,
    env: Optional[Dict[str, str]] = None,
    args: Optional[Iterable[str]] = None,
    network: Optional[str] = None,
    user: Optional[str] = None,
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
    :param user: Optional ``uid:gid`` to run as (``--user``), overriding the image's own ``USER``.
    :param check: If True, a non-zero exit code raises ``CalledProcessError``.
    """
    cmd: list[str] = ["docker", "run", "--rm"]
    # Always assign a container name to allow for clean termination on interrupt.
    # If a name was not provided, generate a unique one using a UUID.  This
    # helps us reference the container when sending kill commands.
    container_name = name

    if container_name is None:
        container_name = construct_container_name(image, pipeline_id)
    elif pipeline_id and pipeline_id not in name:
        raise Exception("Incorrect container name, lack of PIPELINE_ID")

    cmd += ["--name", container_name]
    if user:
        cmd += ["--user", user]
    if volumes_from:
        cmd += ["--volumes-from", volumes_from]
    if volumes:
        for host_path, container_path in volumes.items():
            cmd += ["-v", f"{host_path}:{container_path}"]
    if env:
        for k, v in env.items():
            cmd += ["-e", f"{k}={v}"]
    if network:
        cmd += ["--network", network]
    # Append image and any additional arguments
    cmd += [image]
    if args:
        cmd += list(args)

    run_logged_cmd(cmd, f"[{image}] ")


def image_runtime_user(image: str) -> Optional[Tuple[int, int]]:
    """Return the ``(uid, gid)`` an image runs as, or None when it pins no numeric identity.

    A step that hands the container files it owns has to know who will read them. Only a numeric
    ``USER`` answers that here: a user name would have to be resolved against the image's own
    /etc/passwd. The gid is ``-1`` -- "leave unchanged" for ``os.chown`` -- when the image names
    only a user, because Docker then takes the group from inside the image.
    """
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Config.User}}", image],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    user, _, group = result.stdout.strip().partition(":")
    if not user.isdigit():
        return None
    return int(user), int(group) if group.isdigit() else -1


def image_label(image: str, label: str) -> Optional[str]:
    """Return one label of a local image, or None when the image or the label is absent."""
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", f'{{{{index .Config.Labels "{label}"}}}}', image],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    # An image with no labels at all makes the template print Go's zero value for a nil map.
    value = result.stdout.strip()
    return None if value in ("", "<no value>") else value


def build_source_digest(paths: Iterable[str]) -> str:
    """Digest the package files an image is built from.

    An image whose Dockerfile copies this package carries our own code, so "the tag exists" is not
    "the tag matches the code that talks to it": the tag is reused across builds, and a host that
    already has it keeps running whatever was built there first. That is how a connector image
    stayed a protocol revision behind the caller writing its input file. Paths are relative to the
    package root -- the same anchor build contexts use -- and directories are digested whole,
    because that is what COPY takes.
    """
    digest = hashlib.sha256()
    for relative in sorted(paths):
        declared = Path(relative)
        source = declared if declared.is_absolute() else PACKAGE_ROOT / declared
        if source.is_dir():
            files = sorted(
                item for item in source.rglob("*")
                if item.is_file() and "__pycache__" not in item.parts
            )
        else:
            files = [source]
        for item in files:
            # Relative to the package root so the digest of one revision is the same in the
            # Celery worker, in the builder image, and on the host.
            digest.update(os.path.relpath(item, PACKAGE_ROOT).encode("utf-8"))
            digest.update(b"\0")
            digest.update(item.read_bytes())
    return digest.hexdigest()


def resolve_build_context(dockerfile_dir: str) -> str:
    """Return the build context for a catalog entry.

    Catalog paths are relative to this package root, because that is the one thing every caller
    shares: inside the builder image the root is mounted at /app (`COPY pipeline/ /app/pipeline`,
    `COPY Dockerfiles /app/Dockerfiles`), while the Celery worker has it under the platform
    project. An absolute path is honoured as given, for a caller that supplies its own context.
    """
    path = Path(dockerfile_dir)
    context = path if path.is_absolute() else Path(PACKAGE_ROOT) / path
    if not context.is_dir():
        detail = f"Build context '{dockerfile_dir}' does not exist (resolved to '{context}')."
        raise BuildContextNotFoundError(detail)
    return str(context)


def ensure_image(
    image: str,
    dockerfile_dir: str,
    *,
    build_context: Optional[str] = None,
    timeout: Optional[float] = None,
    source_digest: Optional[str] = None,
) -> None:
    """Build the image if it is not present locally, or if it no longer matches its sources.

    Nothing in the runtime deployment builds analyzer or connector images: compose declares only
    the platform's own services, so a step that does not do this cannot run at all on a fresh
    host.

    A caller whose image packages our own code passes ``source_digest`` (see
    ``build_source_digest``). The digest is stamped on the built image, so presence of the tag is
    no longer taken as proof that it was built from the code now asking for it -- an updated
    checkout rebuilds instead of running the previous revision under the same tag.
    """
    if image_exists(image):
        if source_digest is None or image_label(image, SOURCE_DIGEST_LABEL) == source_digest:
            log.debug("Image '%s' already exists; skipping build", image)
            return
        log.info("Image '%s' was built from other sources than this revision; rebuilding", image)
    log.info("Building image '%s'...", image)
    build_args: Dict[str, str] = {}
    log_level_env = os.environ.get("LOG_LEVEL")
    if log_level_env:
        build_args["LOG_LEVEL"] = log_level_env
    # Most steps ship a self-contained Dockerfile, so its directory is also the build context.
    # A step whose Dockerfile copies from the package (the DAST connector does: `COPY pipeline/`)
    # declares a wider context and is then built with -f, exactly as CI builds it.
    if build_context is None:
        context_dir = resolve_build_context(dockerfile_dir)
        dockerfile = None
    else:
        context_dir = resolve_build_context(build_context)
        dockerfile = str(Path(resolve_build_context(dockerfile_dir)) / "Dockerfile")
    build_image(
        image_name=image,
        context_dir=context_dir,
        dockerfile=dockerfile,
        build_args=build_args,
        labels={SOURCE_DIGEST_LABEL: source_digest} if source_digest else None,
        timeout=timeout,
    )


def _require_shared_path(host_path: str) -> None:
    resolved = Path(host_path).resolve()
    shared_root = Path(HOST_SHARED_ROOT).resolve()
    if resolved != shared_root and shared_root not in resolved.parents:
        detail = (
            f"'{host_path}' is not under the host-shared root '{shared_root}'. "
            "The Docker daemon resolves bind-mount sources on the host, so it would mount an "
            "empty directory instead of this content."
        )
        raise UnsharedWorkspaceError(detail)


@contextmanager
def pipeline_workspace(pipeline_id: str) -> Iterator[Path]:
    """Allocate a per-run directory both this container and the Docker daemon can read."""
    root = Path(HOST_SHARED_ROOT) / "runs"
    root.mkdir(parents=True, exist_ok=True)
    workspace = root / f"{pipeline_id}-{uuid.uuid4().hex[:8]}"
    workspace.mkdir(mode=0o700)
    try:
        yield workspace
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def run_pipeline_container(
    *,
    image: str,
    dockerfile_dir: str,
    pipeline_id: str,
    build_context: Optional[str] = None,
    volumes: Optional[Dict[str, str]] = None,
    env: Optional[Dict[str, str]] = None,
    args: Optional[Iterable[str]] = None,
    network: Optional[str] = None,
    volumes_from: Optional[str] = None,
    user: Optional[str] = None,
) -> subprocess.CompletedProcess | None:
    """Run one containerized pipeline step under the contract every step shares.

    The contract is what each caller used to re-implement, or skip: the image exists, the
    container name is one dockerd accepts, and every bind-mount source is readable by the
    daemon. Call this rather than `run_container` directly.

    One deliberate exception: `project_builder` builds its image on every run with per-project
    build args (not "build if absent") and mounts the Docker socket, which is not step data and
    lives outside the shared root. It uses `run_container` directly and says so at that call.
    """
    ensure_image(image, dockerfile_dir, build_context=build_context)
    for host_path in (volumes or {}):
        _require_shared_path(host_path)
    return run_container(
        image=image,
        pipeline_id=pipeline_id,
        volumes=volumes,
        env=env,
        args=args,
        network=network,
        volumes_from=volumes_from,
        user=user,
    )


def build_image(
    *,
    image_name: str,
    context_dir: str,
    dockerfile: Optional[str] = None,
    build_args: Optional[Dict[str, str]] = None,
    labels: Optional[Dict[str, str]] = None,
    check: bool = True,
    default_log_level: str = "INFO",
    timeout: Optional[float] = None,
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
    :param labels: Mapping of image labels to record on the result (passed via ``--label``).
    :param check: If True, raise ``CalledProcessError`` for non-zero exit codes.
    :param timeout: Optional cap in seconds. A build that hangs would otherwise hold the calling
        worker forever; callers that run inside a Celery task pass one.
    """
    cmd: list[str] = ["docker", "build"]
    # Append build-arg flags
    if build_args:
        for k, v in build_args.items():
            cmd += ["--build-arg", f"{k}={v}"]
    if labels:
        for k, v in labels.items():
            cmd += ["--label", f"{k}={v}"]
    # Tag name
    cmd += ["-t", image_name]
    # Custom Dockerfile if provided
    if dockerfile:
        cmd += ["-f", dockerfile]
    # Context directory
    cmd += ["."]

    # Function to log each build line
    def log_build_line(line: str, log_level: str) -> None:
        if not line:
            return
        txt = line.strip()
        lower = txt.lower()
        if " error " in lower or " failed " in lower:
            log.error(f"[build {image_name}] {txt}")
        else:
            if log_level == "INFO":
                log.info(f"[build {image_name}] {txt}")
            else:
                log.debug(f"[build {image_name}] {txt}")

    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        cwd=context_dir,
        bufsize=1,
    ) as proc:
        assert proc.stdout is not None
        for line in proc.stdout:
            log_build_line(line, default_log_level)
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise
        if check and returncode != 0:
            raise subprocess.CalledProcessError(returncode, cmd)

def _run_git(project_path: str, args: list[str]) -> str | None:
    try:
        cp = subprocess.run(
            ["git", "-C", project_path] + args,
            check=False,
            capture_output=True,
            text=True,
        )
        if cp.returncode != 0:
            return None
        out = (cp.stdout or "").strip()
        return out or None
    except Exception:
        return None


def collect_git_metadata(project_path: str) -> dict:
    """
    Collect exact git metadata from the checked out repository inside builder.
    Works only if `project_path/.git` exists.
    """
    meta: dict = {"is_git": False}

    # quick check
    if not project_path:
        return meta
    if not os.path.isdir(os.path.join(project_path, ".git")):
        return meta

    meta["is_git"] = True

    head = _run_git(project_path, ["rev-parse", "HEAD"])
    if head:
        meta["resolved_commit"] = head

    # branch can be empty if detached
    branch = _run_git(project_path, ["symbolic-ref", "-q", "--short", "HEAD"])
    if branch:
        meta["resolved_branch"] = branch
    else:
        meta["resolved_branch"] = ""

    describe = _run_git(project_path, ["describe", "--tags", "--always", "--dirty"])
    if describe:
        meta["describe"] = describe

    return meta

def cleanup_pipeline_containers(pipeline_id: str) -> None:
    """Remove all Docker containers associated with the given pipeline ID.

    Containers launched by :func:`run_container` include the pipeline ID in
    their names (``sast_<image>_<pipeline_id>``; see
    :func:`construct_container_name`). This helper lists all such
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
                f"name={pipeline_id}",
                "--format",
                "{{.Names}}",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        for name in names:
            cleanup_container(name)
    except Exception as exc:
        log.warning("Failed to clean up pipeline containers for %s: %s", pipeline_id, exc)


def cleanup_container(name: str) -> None:
    """Stop and remove one container by its exact name.

    Stop first, remove second: `rm -f` alone is a SIGKILL, and a live connector needs its shutdown
    to write the recovery and outcome files a resumed run reads. Removal is still required -- a
    leftover name blocks the next run.

    Prefer this over :func:`cleanup_pipeline_containers`, whose substring match also covers
    containers owned by somebody else, the per-execution VPN sidecar among them.
    """
    if not name:
        return
    try:
        run_logged_cmd(["docker", "stop", name])
        run_logged_cmd(["docker", "rm", "-f", name])
        log.info("Stopped and removed pipeline container %s", name)
    except Exception as exc:
        log.warning("Failed to stop and remove container %s: %s", name, exc)
