"""Tests for the ``pipeline.analyzer_runner`` module.

These tests exercise the high‑level behaviour of the helper functions
used to build analyzer images, run analyzers in Docker and select
which analyzers to launch.  External side effects such as actual
Docker image builds or container execution are stubbed out with
monkeypatches so that the tests run quickly and deterministically.

Note that the ``pipeline`` package must be importable via the
``conftest`` helper which prepends the project root to ``sys.path``.
"""

import json
import os
from pathlib import Path
import yaml
import pipeline.analyzer_runner as ar

import pytest


def test_build_image_if_needed_skips_when_image_exists(monkeypatch):
    """When the image already exists, ``build_image_if_needed`` should not
    invoke the build helper on docker_utils."""

    calls = []
    # Pretend the image already exists
    monkeypatch.setattr(ar.docker_utils, "image_exists", lambda name: True)
    # Record any attempted build calls
    monkeypatch.setattr(ar.docker_utils, "build_image", lambda *args, **kwargs: calls.append((args, kwargs)))

    ar.build_image_if_needed("img", "/context")
    # build_image must not have been called
    assert calls == []


def test_build_image_if_needed_builds_with_and_without_log_level(monkeypatch):
    """When the image does not exist the helper should call ``build_image``
    with appropriate arguments and include the LOG_LEVEL environment
    variable as a build argument if present."""

    captured = []

    def fake_build_image(*, image_name, context_dir, dockerfile=None, build_args=None, check=True, default_log_level="DEBUG"):
        # Capture the build invocation for later inspection
        captured.append({
            "image_name": image_name,
            "context_dir": context_dir,
            "dockerfile": dockerfile,
            "build_args": build_args,
            "check": check,
            "default_log_level": default_log_level,
        })

    monkeypatch.setattr(ar.docker_utils, "image_exists", lambda name: False)
    monkeypatch.setattr(ar.docker_utils, "build_image", fake_build_image)
    # First call with no LOG_LEVEL set
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    ar.build_image_if_needed("img1", "/ctx1")
    assert captured[-1]["image_name"] == "img1"
    assert captured[-1]["context_dir"] == "/ctx1"
    # build_args is either None or empty when LOG_LEVEL is not defined
    assert captured[-1]["build_args"] in (None, {})
    # Now call with a LOG_LEVEL defined
    captured.clear()
    monkeypatch.setenv("LOG_LEVEL", "TRACE")
    ar.build_image_if_needed("img2", "/ctx2")
    assert captured[-1]["image_name"] == "img2"
    assert captured[-1]["context_dir"] == "/ctx2"
    # build_args should contain the propagated LOG_LEVEL
    assert captured[-1]["build_args"] == {"LOG_LEVEL": "TRACE"}


def test_run_docker_with_builder_container(monkeypatch):
    """Verify that ``run_docker`` invokes the Docker run helper with
    volumes inherited from a builder container and passes through
    environment variables correctly."""

    calls = []

    def fake_run_container(*, image, volumes_from=None, volumes=None, env=None, args=None):
        calls.append({
            "image": image,
            "volumes_from": volumes_from,
            "volumes": volumes,
            "env": env,
            "args": args,
        })

    monkeypatch.setattr(ar.docker_utils, "run_container", fake_run_container)
    # Define an environment variable required by the analyzer
    monkeypatch.setenv("TOKEN", "secret")
    ar.run_docker(image="analyzer_img", builder_container="builder-cont", args=["input", "output"], project_path="/proj", output_dir="/out", env_vars=["TOKEN"])
    call = calls[-1]
    assert call["image"] == "analyzer_img"
    # volumes_from should be set when a builder container is provided
    assert call["volumes_from"] == "builder-cont"
    # Individual environment variables are propagated from os.environ
    assert call["env"] == {"TOKEN": "secret"}
    # When volumes_from is used, explicit volumes mapping is None
    assert call["volumes"] is None
    # Additional arguments are passed through unchanged
    assert call["args"] == ["input", "output"]


def test_run_docker_without_builder_container(monkeypatch, tmp_path):
    """If no builder container name is supplied, ``run_docker`` should
    construct a volume mapping for the project and output directories
    and include any requested environment variables."""

    calls = []

    def fake_run_container(*, image, volumes_from=None, volumes=None, env=None, args=None):
        calls.append({
            "image": image,
            "volumes_from": volumes_from,
            "volumes": volumes,
            "env": env,
            "args": args,
        })

    monkeypatch.setattr(ar.docker_utils, "run_container", fake_run_container)
    # Setup directories
    project_dir = tmp_path / "project"
    output_dir = tmp_path / "out"
    project_dir.mkdir()
    output_dir.mkdir()
    # Define environment variable
    monkeypatch.setenv("API_KEY", "xyz")
    ar.run_docker(
        image="img",
        builder_container="",  # falsy value means no builder container
        args=["a", "b"],
        project_path=str(project_dir),
        output_dir=str(output_dir),
        env_vars=["API_KEY"],
    )
    call = calls[-1]
    assert call["volumes_from"] is None
    # The volumes mapping should mount the absolute project and output paths into the container
    assert call["volumes"] == {
        str(project_dir.resolve()): "/workspace",
        str(output_dir.resolve()): "/shared/output",
    }
    assert call["env"] == {"API_KEY": "xyz"}
    assert call["args"] == ["a", "b"]


def test_run_docker_missing_env_raises(monkeypatch):
    """If a required environment variable is absent, ``run_docker`` should
    raise an exception instead of silently continuing."""

    # Ensure the environment variable is not set
    monkeypatch.delenv("MISSING", raising=False)
    with pytest.raises(Exception):
        ar.run_docker("img", "builder", ["x"], "/p", "/o", ["MISSING"])


@pytest.mark.parametrize(
    "value, default, expected",
    [
        ("1", False, True),
        ("true", False, True),
        ("yes", False, True),
        ("on", False, True),
        ("0", True, False),
        ("false", True, False),
        ("no", True, False),
        ("off", True, False),
        (None, True, True),
        (None, False, False),
        ("other", False, False),
        ("other", True, True),
    ],
)
def test_env_flag(monkeypatch, value, default, expected):
    """Parametrized test for various truthy and falsy values parsed by
    ``env_flag``.  Unknown strings fall back to the provided default."""

    if value is None:
        monkeypatch.delenv("FLAG", raising=False)
    else:
        monkeypatch.setenv("FLAG", value)
    assert ar.env_flag("FLAG", default) is expected


def test_run_selected_analyzers_exclude_slow(monkeypatch, tmp_path):
    """Only analyzers that are enabled and not marked as slow should be
    launched when ``exclude_slow`` is True."""
    config = {
        "analyzers": [
            {
                "name": "fast_one",
                "image": "img1",
                "enabled": True,
                "time_class": "fast",
                "type": "default",
            },
            {
                "name": "slow_one",
                "image": "img2",
                "enabled": True,
                "time_class": "slow",
                "type": "default",
            },
            {
                "name": "disabled_one",
                "image": "img3",
                "enabled": False,
                "time_class": "medium",
                "type": "default",
            },
        ]
    }
    cfg_path = tmp_path / "analyzers.yaml"
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.dump(config, fh)
    build_calls = []
    run_calls = []
    monkeypatch.setattr(ar, "build_image_if_needed", lambda image_name, dockerfile_dir: build_calls.append((image_name, dockerfile_dir)))
    monkeypatch.setattr(
        ar,
        "run_docker",
        lambda image, builder_container, args, project_path, output_dir, env_vars: run_calls.append((image, builder_container, args, project_path, output_dir, env_vars)),
    )
    out_dir = tmp_path / "out"
    # Ensure the output directory exists prior to invocation
    out_dir.mkdir()
    res = ar.run_selected_analyzers(
        config_path=str(cfg_path),
        analyzers_to_run=None,
        exclude_slow=True,
        project_path=str(tmp_path / "proj"),
        output_dir=str(out_dir),
        builder_container="builder",
        log_level=None,
    )
    # Only the fast analyzer should be run
    assert len(build_calls) == 1
    assert build_calls[0][0] == "img1"
    assert len(run_calls) == 1
    assert run_calls[0][0] == "img1"
    # The function returns None for success
    assert res is None
    # The launch_description file should reflect the launched analyzer
    with open(out_dir / "launch_description.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["launched_analyzers"] == ["fast_one"]
        assert data["project_path"] == str(tmp_path / "proj")


def test_run_selected_analyzers_specific_list(monkeypatch, tmp_path):
    """Selecting a subset of analyzers by name should run only those
    analyzers that are enabled and present in the list."""
    config = {
        "analyzers": [
            {
                "name": "a",
                "image": "img_a",
                "enabled": True,
                "time_class": "fast",
                "type": "default",
            },
            {
                "name": "b",
                "image": "img_b",
                "enabled": True,
                "time_class": "medium",
                "type": "default",
            },
        ]
    }
    cfg_path = tmp_path / "analyzers.yaml"
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.dump(config, fh)
    build_calls = []
    run_calls = []
    monkeypatch.setattr(ar, "build_image_if_needed", lambda image_name, dockerfile_dir: build_calls.append(image_name))
    monkeypatch.setattr(
        ar,
        "run_docker",
        lambda image, builder_container, args, project_path, output_dir, env_vars: run_calls.append(image),
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    ar.run_selected_analyzers(
        config_path=str(cfg_path),
        analyzers_to_run=["b"],
        exclude_slow=False,
        project_path=str(tmp_path / "proj"),
        output_dir=str(out_dir),
        builder_container="builder",
        log_level=None,
    )
    # Only analyzer b should be built and run
    assert build_calls == ["img_b"]
    assert run_calls == ["img_b"]


def test_run_selected_analyzers_skip_builder_on_non_compile_project(monkeypatch, tmp_path):
    """Analyzers of type ``builder`` should be skipped when
    NON_COMPILE_PROJECT environment variable is truthy."""
    import yaml
    import pipeline.analyzer_runner as ar
    config = {
        "analyzers": [
            {
                "name": "builder_one",
                "image": "img1",
                "enabled": True,
                "time_class": "fast",
                "type": "builder",
            },
            {
                "name": "normal_one",
                "image": "img2",
                "enabled": True,
                "time_class": "medium",
                "type": "default",
            },
        ]
    }
    cfg_path = tmp_path / "analyzers.yaml"
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.dump(config, fh)
    build_calls = []
    run_calls = []
    monkeypatch.setattr(ar, "build_image_if_needed", lambda image_name, dockerfile_dir: build_calls.append(image_name))
    monkeypatch.setattr(
        ar,
        "run_docker",
        lambda image, builder_container, args, project_path, output_dir, env_vars: run_calls.append(image),
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    # Set NON_COMPILE_PROJECT so that builder analyzers are skipped
    monkeypatch.setenv("NON_COMPILE_PROJECT", "1")
    ar.run_selected_analyzers(
        config_path=str(cfg_path),
        analyzers_to_run=None,
        exclude_slow=False,
        project_path=str(tmp_path / "proj"),
        output_dir=str(out_dir),
        builder_container="builder",
        log_level=None,
    )
    # Normal analyzer should have been built and run
    assert build_calls == ["img2"]
    assert run_calls == ["img2"]


def test_run_selected_analyzers_no_analyzers(monkeypatch, tmp_path):
    """If there are no enabled analyzers after filtering, the function
    should warn and return ``None`` without invoking docker helpers."""
    import yaml
    import pipeline.analyzer_runner as ar
    config = {
        "analyzers": [
            {
                "name": "slow_one",
                "image": "img1",
                "enabled": True,
                "time_class": "slow",
                "type": "default",
            }
        ]
    }
    cfg_path = tmp_path / "analyzers.yaml"
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.dump(config, fh)
    build_calls = []
    run_calls = []
    monkeypatch.setattr(ar, "build_image_if_needed", lambda image_name, dockerfile_dir: build_calls.append(image_name))
    monkeypatch.setattr(
        ar,
        "run_docker",
        lambda image, builder_container, args, project_path, output_dir, env_vars: run_calls.append(image),
    )
    # Exclude slow analyzers so that none remain
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = ar.run_selected_analyzers(
        config_path=str(cfg_path),
        analyzers_to_run=None,
        exclude_slow=True,
        project_path=str(tmp_path / "proj"),
        output_dir=str(out_dir),
        builder_container="builder",
        log_level=None,
    )
    # No builds or runs should occur
    assert build_calls == []
    assert run_calls == []
    # Function returns None when nothing to do
    assert res is None


def test_run_selected_analyzers_log_level_injected(monkeypatch, tmp_path):
    """If a log level is passed to ``run_selected_analyzers`` the
    ``LOG_LEVEL`` environment variable should be included in the env
    vars passed to the analyzer container."""
    import yaml
    import pipeline.analyzer_runner as ar
    config = {
        "analyzers": [
            {
                "name": "x",
                "image": "imgx",
                "enabled": True,
                "time_class": "fast",
                "type": "default",
                "env": [],
            }
        ]
    }
    cfg_path = tmp_path / "analyzers.yaml"
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.dump(config, fh)
    captured_envs = []

    def fake_run_docker(image, builder_container, args, project_path, output_dir, env_vars):
        captured_envs.append(list(env_vars))

    # Monkeypatch build and run helpers
    monkeypatch.setattr(ar, "build_image_if_needed", lambda image_name, dockerfile_dir: None)
    monkeypatch.setattr(ar, "run_docker", fake_run_docker)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    # Provide a LOG_LEVEL in the environment so that it can be propagated
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    ar.run_selected_analyzers(
        config_path=str(cfg_path),
        analyzers_to_run=None,
        exclude_slow=False,
        project_path=str(tmp_path / "proj"),
        output_dir=str(out_dir),
        builder_container="builder",
        log_level="INFO",
    )
    # ``LOG_LEVEL`` should appear in env_vars list passed to run_docker
    assert captured_envs and "LOG_LEVEL" in captured_envs[0]