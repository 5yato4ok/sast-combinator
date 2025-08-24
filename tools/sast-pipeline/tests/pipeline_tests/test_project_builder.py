"""Tests for the ``pipeline.project_builder`` module.

These tests exercise the high‑level flow for building a project
environment image and launching the builder container.  External side
effects such as interacting with Docker or the filesystem are
monkeypatched so the tests run deterministically without requiring a
Docker daemon.  The goal is to verify that the correct helper
functions are invoked with appropriate arguments and that the
returned metadata reflects the expected structure.

The ``pipeline`` package is made importable via the ``conftest``
fixture which adds the project root to ``sys.path``.
"""

import json
import os
from pathlib import Path
from collections import Counter
import types

import pytest
import pipeline.project_builder as pb
import pipeline.docker_utils as du


def make_dummy_analyzer_config(images=None, tmp_cfg_path="/tmp/fake_cfg.yaml"):
    """Create a simple dummy object to stand in for
    ``AnalyzersConfigHelper`` in project_builder tests.

    :param images: Optional iterable of image names returned by
        ``get_all_images``.  Defaults to an empty list.
    :param tmp_cfg_path: Path returned by ``prepare_pipeline_analyzer_config``.
    :return: An object with ``get_all_images`` and
        ``prepare_pipeline_analyzer_config`` methods.
    """
    class DummyCfg:
        def __init__(self, imgs, path):
            self.imgs = imgs
            self.cfg_path = path

        def get_all_images(self):
            return set(self.imgs)

        def prepare_pipeline_analyzer_config(self, languages, max_time_class, target_analyzers):
            # ignore parameters and return a constant path
            return self.cfg_path

    return DummyCfg(images or [], tmp_cfg_path)


def test_configure_project_run_analyses_happy_path(monkeypatch, tmp_path):
    """A normal run should build the builder image, invoke the builder
    container and return metadata including the path to the launch
    description.

    This test patches out Docker helpers and file operations so that
    nothing is actually executed.  It verifies that the correct
    arguments are passed to the helpers and that the returned
    dictionary contains expected keys.
    """

    # Fix the timestamp so that the output directory is deterministic
    class FixedDatetime:
        @classmethod
        def now(cls):
            # Fixed date/time for reproducibility
            from datetime import datetime
            return datetime(2020, 1, 1, 12, 34, 56)

    monkeypatch.setattr(pb, "datetime", FixedDatetime)

    # Create a temporary script file that will be copied into the build context
    script = tmp_path / "proj_config.py"
    script.write_text("print('hello')")
    # Create a fake build context directory
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    # Create the dummy analyzer config
    dummy_cfg_path = str(tmp_path / "analyzers_out.yaml")
    analyzer_cfg = make_dummy_analyzer_config(images=["img_a", "img_b"], tmp_cfg_path=dummy_cfg_path)

    # Capture calls to docker helper functions
    build_calls = []
    delete_calls = []
    run_calls = []
    construct_calls = []

    # Patch delete_image_if_exist to record image names
    monkeypatch.setattr(du, "delete_image_if_exist", lambda image: delete_calls.append(image))

    # Patch build_image to record build invocations
    def fake_build_image(*, image_name, context_dir, dockerfile=None, build_args=None, check=True, default_log_level="DEBUG"):
        build_calls.append({
            "image_name": image_name,
            "context_dir": context_dir,
            "dockerfile": dockerfile,
            "build_args": build_args,
            "check": check,
            "default_log_level": default_log_level,
        })
    monkeypatch.setattr(du, "build_image", fake_build_image)

    # Deterministic container name and pipeline id
    monkeypatch.setenv("PIPELINE_ID", "pid")
    def fake_construct_container_name(image):
        name = f"sast_pid_{image}_uuid"
        construct_calls.append((image, name))
        return name, "pid"
    monkeypatch.setattr(du, "construct_container_name", fake_construct_container_name)

    # Patch run_container to record environment and volume mappings
    def fake_run_container(*, image, name=None, volumes=None, volumes_from=None, env=None, args=None):
        # Simulate the analyzer writing the launch description file
        out_path = volumes[os.path.abspath("/tmp/my_project")] if volumes else None
        # Create launch_description.json inside the output_dir
        # The test harness uses timestamp 20200101_123456 -> output dir ends with that
        for host_path, container_path in volumes.items():
            if container_path == "/shared/output":
                launch_file = Path(host_path) / "launch_description.json"
                launch_data = {"launched_analyzers": ["dummy"], "project_path": os.path.abspath("/tmp/my_project")}
                launch_file.write_text(json.dumps(launch_data))
        run_calls.append({
            "image": image,
            "name": name,
            "volumes": volumes,
            "volumes_from": volumes_from,
            "env": env,
        })
    monkeypatch.setattr(du, "run_container", fake_run_container)

    # Execute the function under test
    result = pb.configure_project_run_analyses(
        script_path=str(script),
        output_dir=str(tmp_path / "out"),
        languages=["py"],
        analyzer_config=analyzer_cfg,
        dockerfile_path="Dockerfile",
        context_dir=str(context_dir),
        image_name="builder-img",
        project_path="/tmp/my_project",
        force_rebuild=False,
        rebuild_images=False,
        version="1.2.3",
        log_level="WARNING",
        min_time_class="slow",
    )

    # Verify that the builder image was built once with the expected build arg
    assert len(build_calls) == 1
    build = build_calls[0]
    assert build["image_name"] == "builder-img"
    assert build["context_dir"] == str(context_dir)
    # The build args should include the relative project config path
    assert "PROJECT_CONFIG_PATH" in build["build_args"]
    # delete_image_if_exist should not have been called since rebuild_images=False
    assert delete_calls == []
    # The container should have been run once
    assert len(run_calls) == 1
    run_info = run_calls[0]
    # The container name should start with the fixed pipeline prefix and image name
    assert run_info["name"].startswith("sast_pid_builder-img")
    # Environment variables should include FORCE_REBUILD=0, BUILDER_CONTAINER, LOG_LEVEL, PROJECT_VERSION, PIPELINE_ID
    env = run_info["env"]
    assert env["FORCE_REBUILD"] == "0"
    assert "BUILDER_CONTAINER" in env
    assert env["LOG_LEVEL"] == "WARNING"
    assert env["PROJECT_VERSION"] == "1.2.3"
    assert env["PIPELINE_ID"] == "pid"
    # The volumes mapping should include the project path, output directory and config file
    vols = run_info["volumes"]
    assert os.path.abspath("/tmp/my_project") in vols
    # The returned result should contain keys for the output and temp config path
    assert result["is_correct"] is True
    assert Path(result["output_dir"]).name.endswith("20200101_123456")
    assert result["tmp_analyzer_config_path"] == dummy_cfg_path
    # The trim_path should equal the original project_path in the launch_description file
    assert result["trim_path"] == os.path.abspath("/tmp/my_project")


def test_configure_project_run_analyses_missing_script(monkeypatch, tmp_path):
    """If the provided script path does not exist, a FileNotFoundError should
    be raised before any Docker commands are issued."""
    # Create dummy config helper
    analyzer_cfg = make_dummy_analyzer_config()
    # Patch docker helpers to assert they are not called
    monkeypatch.setattr(du, "build_image", lambda **kwargs: pytest.fail("build_image should not be called"))
    # Use a non‑existent file path
    script_path = tmp_path / "nope.sh"
    with pytest.raises(FileNotFoundError):
        pb.configure_project_run_analyses(
            script_path=str(script_path),
            output_dir=str(tmp_path / "out"),
            languages=["py"],
            analyzer_config=analyzer_cfg,
            dockerfile_path="Dockerfile",
            context_dir=str(tmp_path),
        )


def test_configure_project_run_analyses_force_rebuild(monkeypatch, tmp_path):
    """When force_rebuild is True, the FORCE_REBUILD env var should be set
    to "1"."""
    analyzer_cfg = make_dummy_analyzer_config()
    # Create script file
    script = tmp_path / "cfg.py"
    script.write_text("print('x')")
    # Create context directory
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    monkeypatch.setenv("PIPELINE_ID", "pid")
    # Patch Docker helper methods
    monkeypatch.setattr(du, "build_image", lambda **kwargs: None)
    monkeypatch.setattr(du, "construct_container_name", lambda img: (f"sast_pid_{img}_uuid", "pid"))
    captured_env = {}
    def fake_run_container(*, image, name=None, volumes=None, volumes_from=None, env=None, args=None):
        captured_env.update(env)
    monkeypatch.setattr(du, "run_container", fake_run_container)
    pb.configure_project_run_analyses(
        script_path=str(script),
        output_dir=str(tmp_path / "out"),
        languages=["py"],
        analyzer_config=analyzer_cfg,
        dockerfile_path="Dockerfile",
        context_dir=str(ctx),
        force_rebuild=True,
    )
    assert captured_env.get("FORCE_REBUILD") == "1"


def test_configure_project_run_analyses_rebuild_images(monkeypatch, tmp_path):
    """When ``rebuild_images`` is True the builder image and all analyzer
    images should be removed before building."""
    # Dummy config returns images to delete
    analyzer_cfg = make_dummy_analyzer_config(images=["i1", "i2"])
    # Create script and context
    script = tmp_path / "setup.py"
    script.write_text("print('setup')")
    ctx = tmp_path / "c"
    ctx.mkdir()
    # Record deletion calls
    deleted = []
    monkeypatch.setattr(du, "delete_image_if_exist", lambda img: deleted.append(img))
    # Stub other docker utils
    monkeypatch.setattr(du, "build_image", lambda **kwargs: None)
    monkeypatch.setattr(du, "construct_container_name", lambda img: (f"sast_id_{img}_uuid", "id"))
    monkeypatch.setattr(du, "run_container", lambda **kwargs: None)
    pb.configure_project_run_analyses(
        script_path=str(script),
        output_dir=str(tmp_path / "o"),
        languages=["py"],
        analyzer_config=analyzer_cfg,
        dockerfile_path="Dockerfile",
        context_dir=str(ctx),
        image_name="builder",
        rebuild_images=True,
    )
    # The builder image is deleted after analyzer images
    assert Counter(deleted) == Counter(["i1", "i2", "builder"])


def test_configure_project_run_analyses_cleanup_on_interrupt(monkeypatch, tmp_path):
    """If ``run_container`` raises a KeyboardInterrupt the builder
    function should invoke cleanup_pipeline_containers and re‑raise
    the exception."""
    analyzer_cfg = make_dummy_analyzer_config()
    script = tmp_path / "cfg.py"
    script.write_text("1")
    ctx = tmp_path / "ctx"
    ctx.mkdir()
    # Setup deterministic names
    monkeypatch.setenv("PIPELINE_ID", "pid")
    monkeypatch.setattr(du, "construct_container_name", lambda img: (f"sast_pid_{img}_uuid", "pid"))
    monkeypatch.setattr(du, "build_image", lambda **kwargs: None)
    # Flag to assert cleanup called
    cleanup_called = []
    def fake_cleanup(pid):
        cleanup_called.append(pid)
    monkeypatch.setattr(du, "cleanup_pipeline_containers", fake_cleanup)
    # run_container should raise KeyboardInterrupt
    def fake_run_container(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(du, "run_container", fake_run_container)
    with pytest.raises(KeyboardInterrupt):
        pb.configure_project_run_analyses(
            script_path=str(script),
            output_dir=str(tmp_path / "o"),
            languages=["py"],
            analyzer_config=analyzer_cfg,
            dockerfile_path="Dockerfile",
            context_dir=str(ctx),
            image_name="build",
        )
    # Cleanup should have been invoked with the pipeline id
    assert cleanup_called == ["pid"]