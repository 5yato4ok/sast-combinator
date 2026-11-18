"""Opt-in native Docker evidence for capture, source-only runs, limits and isolation."""

import json
import os
import subprocess
import uuid
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest
import yaml
from pipeline import docker_utils
from pipeline.build_runtime import prepare_build_runtimes
from pipeline.config_utils import AnalyzersConfigHelper

pytestmark = pytest.mark.skipif(
    os.environ.get("SAST_TEST_CODEQL_IMAGE") is None,
    reason="Requires native amd64 Docker and CodeQL image build",
)
PACKAGE = Path(__file__).resolve().parents[2]
FIXTURE = PACKAGE / "tests" / "fixtures" / "build_runtime"


@dataclass(frozen=True, slots=True)
class NativeImages:
    builder: str = "sast-builder-runtime-test:verification"
    source_analyzer: str = "sast-source-runtime-test:verification"


@pytest.fixture(scope="module")
def native_images():
    images = NativeImages()
    docker_utils.build_image(
        image_name=images.builder, context_dir=str(PACKAGE),
        dockerfile="Dockerfiles/builder/Dockerfile",
        build_args={"PROJECT_CONFIG_PATH": "tests/fixtures/build_runtime/init.sh"},
    )
    docker_utils.build_image(
        image_name=images.source_analyzer, context_dir=str(PACKAGE),
        dockerfile="tests/fixtures/build_runtime/source_analyzer.Dockerfile",
    )
    return images


def _volume_exists(volume):
    return subprocess.run(
        ["docker", "volume", "inspect", volume], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def _read_json(image, volume, filename):
    result = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-v", f"{volume}:/results:ro", "--entrypoint", "cat",
         image, f"/results/{filename}"], text=True, capture_output=True, check=True,
    )
    return json.loads(result.stdout)


def _analyzers(images, source_only):
    codeql = next(item for item in AnalyzersConfigHelper().get_analyzers() if item["name"] == "codeql_cpp")
    codeql["image"] = os.environ["SAST_TEST_CODEQL_IMAGE"]
    if not source_only:
        return [codeql]
    # Provisioning this deliberately unavailable runtime must be unnecessary after source-only init.
    codeql.update(image="unavailable-build-runtime:test", dockerfile_path="/nonexistent-build-context")
    return [codeql, {"name": "source_scan", "image": images.source_analyzer, "result_file": "source.sarif"}]


def _seed_config(image, volume, analyzers, pipeline_id):
    docker_utils.run_container(
        image=image, pipeline_id=pipeline_id, entrypoint="python3", volumes={volume: "/verify"}, network="none",
        args=["-c", "import pathlib, sys; pathlib.Path('/verify/analyzers.yaml').write_text(sys.argv[1]); "
              "pathlib.Path('/verify/check_builder.py').write_text(sys.argv[2])",
              yaml.safe_dump({"analyzers": analyzers}), (FIXTURE / "check_builder.py").read_text()],
    )


@pytest.mark.parametrize("source_only,limited", [(False, True), (True, True), (True, False)])
def test_real_builder_capture_and_separate_analysis(native_images, source_only, limited):
    """Observe reports, effective limits, write denial and reclaimed volumes through real Docker."""
    pipeline_id = uuid.uuid4().hex
    analyzers = _analyzers(native_images, source_only)
    memory, cpus = ("8g", "2") if limited else ("", "")
    expected_limits = {"memory": 8 * 1024**3 if limited else 0, "cpus": 2_000_000_000 if limited else 0}
    with ExitStack() as stack:
        volumes = []
        for _ in range(3):
            volume = f"sast-test-{uuid.uuid4().hex}"
            docker_utils.run_logged_cmd(["docker", "volume", "create", volume])
            stack.callback(docker_utils.cleanup_volume, volume)
            volumes.append(volume)
        workspace, output, config = volumes
        _seed_config(native_images.builder, config, analyzers, pipeline_id)
        runtimes = stack.enter_context(prepare_build_runtimes(analyzers, pipeline_id))
        mounts = {workspace: "/workspace", output: "/shared/output", config: "/verify:ro",
                  "/var/run/docker.sock": "/var/run/docker.sock"}
        for runtime in runtimes:
            mounts.update(runtime.mounts)
        builder_name = docker_utils.construct_container_name(native_images.builder, pipeline_id)
        docker_utils.run_container(
            image=native_images.builder, pipeline_id=pipeline_id, name=builder_name, volumes=mounts,
            entrypoint="/bin/bash",
            args=["-eu", "-c", "python3 /verify/check_builder.py; cp /verify/analyzers.yaml /app/analyzers.yaml; "
                  "exec /app/builder-entrypoint.sh"],
            env={"BUILDER_CONTAINER": builder_name, "PIPELINE_ID": pipeline_id, "LOG_LEVEL": "INFO",
                 "SAST_BUILD_RUNTIMES": json.dumps([asdict(runtime) for runtime in runtimes]),
                 "FIXTURE_SOURCE_ONLY": "1" if source_only else "0", "SAST_ANALYZER_MEMORY": memory,
                 "SAST_ANALYZER_CPUS": cpus, "CODEQL_RAM_MB": "6144", "JOBS": "2"},
            resources=docker_utils.ContainerResources(memory=memory, cpus=cpus),
        )
        observed = _read_json(native_images.builder, output, "builder-check.json")
        scratch = observed.pop("scratch")
        assert scratch["Type"] == "volume"
        assert not _volume_exists(scratch["Name"]), "Temporary capture storage must be reclaimed before report import"
        assert observed == expected_limits
        assert _read_json(native_images.builder, output, "build-environment.json") == {"jobs": 2}
        launch = _read_json(native_images.builder, output, "launch_description.json")
        assert [(item["name"], item["status"]) for item in launch["analyzer_outcomes"]] == [
            ("source_scan" if source_only else "codeql_cpp", "success"),
        ]
        if source_only:
            report = _read_json(native_images.builder, output, "source.sarif")
            assert report["properties"] == expected_limits | {"source_exists": True}
        else:
            report = _read_json(native_images.builder, output, "codeql_cpp.sarif")
            assert sum(len(run.get("results", [])) for run in report["runs"]) > 0
            assert launch["analyzer_versions"][0]["image"].startswith("sha256:")
    assert all(not _volume_exists(volume) for volume in [*volumes, *(item.volume for item in runtimes)])


def test_cancellation_reclaims_only_its_pipeline_runtime(native_images):
    first_id, second_id = uuid.uuid4().hex, uuid.uuid4().hex
    analyzers = _analyzers(native_images, source_only=False)
    with prepare_build_runtimes(analyzers, first_id) as first:
        with prepare_build_runtimes(analyzers, second_id) as second:
            name = docker_utils.construct_container_name(native_images.builder, first_id)
            try:
                subprocess.run(
                    ["docker", "run", "--rm", "-d", "--name", name, "--network", "none", "--memory", "64m",
                     "-v", f"{first[0].volume}:{first[0].root}:ro,nocopy", "--entrypoint", "sleep",
                     native_images.builder, "infinity"], check=True, capture_output=True,
                )
                inspection = json.loads(subprocess.check_output(["docker", "inspect", name], text=True))[0]
                scratch = next(mount["Name"] for mount in inspection["Mounts"] if mount["Destination"] == "/shared/build")
                subprocess.run(
                    ["docker", "run", "--rm", "-d", "--name", f"sast_analysis_{first_id}",
                     "--network", "none", "--memory", "64m", "--volumes-from", name,
                     "--entrypoint", "sleep", native_images.source_analyzer, "infinity"],
                    check=True, capture_output=True,
                )
                docker_utils.cleanup_volume(first[0].volume)
                assert _volume_exists(first[0].volume), "A live builder's runtime must not be removed"
                docker_utils.cleanup_pipeline_containers(first_id)
                assert not docker_utils.container_exists(name)
                assert not _volume_exists(first[0].volume)
                assert not _volume_exists(scratch)
                assert _volume_exists(second[0].volume)
            finally:
                docker_utils.cleanup_pipeline_containers(first_id)


def test_builder_result_survives_another_build_replacing_its_tag(tmp_path):
    """Two environment revisions sharing a builder tag still execute their own image."""
    (tmp_path / "Dockerfile").write_text("FROM ubuntu:24.04\nCOPY revision /revision\n")
    image = f"sast-builder-revision-test:{uuid.uuid4().hex}"
    ids = []
    for revision in ("first", "second"):
        (tmp_path / "revision").write_text(revision)
        iid_file = tmp_path / f"{revision}.iid"
        docker_utils.build_image(image_name=image, context_dir=str(tmp_path), iid_file=str(iid_file))
        ids.append(iid_file.read_text().strip())
    assert ids[0] != ids[1]
    for image_id, revision in zip(ids, ("first", "second")):
        result = subprocess.run(
            ["docker", "run", "--rm", "--network", "none", image_id, "cat", "/revision"],
            check=True, capture_output=True, text=True,
        )
        assert result.stdout == revision
