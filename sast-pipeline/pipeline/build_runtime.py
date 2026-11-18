"""Tools come from analyzer images; capture runs in the initialized builder."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath

from . import docker_utils

RUNTIME_ROOT = PurePosixPath("/opt/sast-tools")
CAPTURE_ROOT = PurePosixPath("/shared/build")


@dataclass(frozen=True, slots=True)
class BuildRuntime:
    """An analyzer-owned directory exported as a read-only volume to the builder."""

    root: str
    capture: str

    def __post_init__(self) -> None:
        root, capture = PurePosixPath(self.root), PurePosixPath(self.capture)
        if root.parent != RUNTIME_ROOT or ".." in root.parts:
            raise ValueError(f"Runtime root must be a direct child of {RUNTIME_ROOT}")
        if not capture.is_relative_to(root) or capture == root or ".." in capture.parts:
            raise ValueError("Capture executable must be inside the analyzer runtime")

    @classmethod
    def from_config(cls, analyzer: dict) -> BuildRuntime | None:
        value = analyzer.get("build_runtime")
        return cls(**value) if value is not None else None


@dataclass(frozen=True, slots=True)
class RuntimeMount:
    root: str
    volume: str

    @property
    def mounts(self) -> dict[str, str]:
        return {self.volume: f"{self.root}:ro,nocopy"}

    @classmethod
    def for_capture(cls, spec: BuildRuntime) -> RuntimeMount:
        runtimes = (cls(**item) for item in json.loads(os.environ.get("SAST_BUILD_RUNTIMES", "[]")))
        for runtime in runtimes:
            if runtime.root == spec.root:
                return runtime
        raise ValueError(f"Builder has no prepared runtime mounted at {spec.root}")


@dataclass(frozen=True, slots=True)
class CapturedBuild:
    image: str
    artifact_dir: str


def _populate_runtime(analyzer: dict, runtime: RuntimeMount, pipeline_id: str) -> str:
    context = str(analyzer.get("dockerfile_path", f"Dockerfiles/{analyzer['name']}"))
    docker_utils.ensure_image(
        str(analyzer["image"]), context,
        source_digest=docker_utils.build_source_digest([context]),
    )
    image = docker_utils.image_id(str(analyzer["image"]))
    if not image:
        raise ValueError(f"Cannot resolve the prepared image for {analyzer['name']}")
    # The builder has mounted this empty volume with nocopy. Docker now populates it
    # from the analyzer image, so skipped build analyzers never need their image built.
    docker_utils.run_container(
        image=image, pipeline_id=pipeline_id, entrypoint="/bin/true",
        volumes={runtime.volume: runtime.root}, network="none",
    )
    return image


@contextmanager
def prepare_build_runtimes(analyzers: list[dict], pipeline_id: str) -> Iterator[tuple[RuntimeMount, ...]]:
    """Reserve empty runtime mounts; populate only after init selects a build analyzer."""
    with ExitStack() as stack:
        prepared: list[RuntimeMount] = []
        for analyzer in analyzers:
            spec = BuildRuntime.from_config(analyzer)
            if spec is None:
                continue
            if any(runtime.root == spec.root for runtime in prepared):
                raise ValueError(f"Multiple analyzers declare the same runtime root: {spec.root}")
            volume = f"sast-runtime-{uuid.uuid4().hex}"
            docker_utils.run_logged_cmd([
                "docker", "volume", "create", "--label", f"com.aist.pipeline-id={pipeline_id}", volume,
            ])
            stack.callback(docker_utils.cleanup_volume, volume)
            prepared.append(RuntimeMount(root=spec.root, volume=volume))
        yield tuple(prepared)


@contextmanager
def capture_build(analyzer: dict, project_path: str, pipeline_id: str) -> Iterator[CapturedBuild]:
    """Execute an image-owned adapter with the environment inherited from project init.

    The project command is intentionally executable configuration, just like init itself.
    It is read by the adapter from the environment, never interpolated into a CLI argument.
    """
    if not os.environ.get("SAST_BUILD_COMMAND", "").strip():
        raise ValueError("A build analyzer requires SAST_BUILD_COMMAND from project init")
    spec = BuildRuntime.from_config(analyzer)
    if spec is None:
        raise ValueError("The analyzer has no build_runtime configuration")
    runtime = RuntimeMount.for_capture(spec)
    image = _populate_runtime(analyzer, runtime, pipeline_id)
    with tempfile.TemporaryDirectory(prefix="build-capture-", dir=CAPTURE_ROOT) as artifacts:
        docker_utils.run_logged_cmd([spec.capture, project_path, artifacts], f"[{analyzer['name']}][capture]")
        yield CapturedBuild(image=image, artifact_dir=artifacts)
