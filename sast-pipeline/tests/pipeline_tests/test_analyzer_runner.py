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


def test_run_docker_with_builder_container(monkeypatch):
    """Verify that ``run_docker`` invokes the Docker run helper with
    volumes inherited from a builder container and passes through
    environment variables correctly."""

    calls = []

    def fake_run_container(*, image, dockerfile_dir="", pipeline_id=None, volumes_from=None, volumes=None, env=None, args=None):
        calls.append({
            "image": image,
            "volumes_from": volumes_from,
            "volumes": volumes,
            "env": env,
            "args": args,
        })

    monkeypatch.setattr(ar.docker_utils, "run_pipeline_container", fake_run_container)
    # Define an environment variable required by the analyzer
    monkeypatch.setenv("TOKEN", "secret")
    ar.run_docker(image="analyzer_img", builder_container="builder-cont", args=["input", "output"], project_path="/proj", output_dir="/out", pipeline_id="pipe1234", env_vars=["TOKEN"])
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

    def fake_run_container(*, image, dockerfile_dir="", pipeline_id=None, volumes_from=None, volumes=None, env=None, args=None):
        calls.append({
            "image": image,
            "volumes_from": volumes_from,
            "volumes": volumes,
            "env": env,
            "args": args,
        })

    monkeypatch.setattr(ar.docker_utils, "run_pipeline_container", fake_run_container)
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
        pipeline_id="pipe1234",
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
        ar.run_docker("img", "builder", ["x"], "/p", "/o", "pipe1234", ["MISSING"])


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
    def fake_run_docker(image, builder_container, args, project_path, output_dir, pipeline_id, env_vars, dockerfile_dir=""):
        # The step ensures its own image, so one call carries both facts.
        build_calls.append((image, dockerfile_dir))
        run_calls.append((image, builder_container, args, project_path, output_dir, env_vars))

    monkeypatch.setattr(ar, "run_docker", fake_run_docker)
    out_dir = tmp_path / "out"
    # Ensure the output directory exists prior to invocation
    out_dir.mkdir()
    res = ar.run_selected_analyzers(
        config_path=str(cfg_path),
        pipeline_id="pipe1234",
        analyzers_to_run=None,
        max_time_class="medium",
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
    def fake_run_docker(image, builder_container, args, project_path, output_dir, pipeline_id, env_vars, dockerfile_dir=""):
        build_calls.append(image)
        run_calls.append(image)

    monkeypatch.setattr(ar, "run_docker", fake_run_docker)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    ar.run_selected_analyzers(
        config_path=str(cfg_path),
        pipeline_id="pipe1234",
        analyzers_to_run=["b"],
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
    def fake_run_docker(image, builder_container, args, project_path, output_dir, pipeline_id, env_vars, dockerfile_dir=""):
        build_calls.append(image)
        run_calls.append(image)

    monkeypatch.setattr(ar, "run_docker", fake_run_docker)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    # Set NON_COMPILE_PROJECT so that builder analyzers are skipped
    monkeypatch.setenv("NON_COMPILE_PROJECT", "1")
    ar.run_selected_analyzers(
        config_path=str(cfg_path),
        pipeline_id="pipe1234",
        analyzers_to_run=None,
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
    def fake_run_docker(image, builder_container, args, project_path, output_dir, pipeline_id, env_vars, dockerfile_dir=""):
        build_calls.append(image)
        run_calls.append(image)

    monkeypatch.setattr(ar, "run_docker", fake_run_docker)
    # Exclude slow analyzers so that none remain
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = ar.run_selected_analyzers(
        config_path=str(cfg_path),
        pipeline_id="pipe1234",
        analyzers_to_run=None,
        max_time_class="medium",
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

    def fake_run_docker(image, builder_container, args, project_path, output_dir, pipeline_id, env_vars, dockerfile_dir=""):
        captured_envs.append(list(env_vars))

    # Monkeypatch build and run helpers
    monkeypatch.setattr(ar, "run_docker", fake_run_docker)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    # Provide a LOG_LEVEL in the environment so that it can be propagated
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    ar.run_selected_analyzers(
        config_path=str(cfg_path),
        pipeline_id="pipe1234",
        analyzers_to_run=None,
        project_path=str(tmp_path / "proj"),
        output_dir=str(out_dir),
        builder_container="builder",
        log_level="INFO",
    )
    # ``LOG_LEVEL`` should appear in env_vars list passed to run_docker
    assert captured_envs and "LOG_LEVEL" in captured_envs[0]


def _single_analyzer_config(tmp_path, name, image):
    config = {
        "analyzers": [
            {
                "name": name,
                "image": image,
                "enabled": True,
                "time_class": "fast",
                "type": "default",
            },
        ]
    }
    cfg_path = tmp_path / "analyzers.yaml"
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.dump(config, fh)
    return cfg_path


def _run(tmp_path, cfg_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    ar.run_selected_analyzers(
        config_path=str(cfg_path),
        pipeline_id="pipe1234",
        analyzers_to_run=None,
        max_time_class="medium",
        project_path=str(tmp_path / "proj"),
        output_dir=str(out_dir),
        builder_container="builder",
        log_level=None,
    )
    with open(out_dir / "launch_description.json", "r", encoding="utf-8") as f:
        return json.load(f)


def test_launch_description_records_which_build_of_the_analyzer_ran(monkeypatch, tmp_path):
    """A rebuilt image changes the scanner silently; the run has to say which build it used."""
    cfg_path = _single_analyzer_config(tmp_path, "semgrep", "sast-semgrep")
    monkeypatch.setattr(ar.docker_utils, "image_id", lambda image: "sha256:feedface")
    monkeypatch.setattr(ar.docker_utils, "image_label", lambda image, label: "semgrep 1.183.0")
    monkeypatch.setattr(
        ar,
        "run_docker",
        lambda image, builder_container, args, project_path, output_dir, pipeline_id, env_vars, dockerfile_dir="": None,
    )

    versions = _run(tmp_path, cfg_path)["analyzer_versions"]
    assert versions == [
        {
            "analyzer": "semgrep",
            "image": "sast-semgrep",
            "image_id": "sha256:feedface",
            "tool_version": "semgrep 1.183.0",
        },
    ]


def test_a_failed_analyzer_still_reports_which_build_it_ran(monkeypatch, tmp_path):
    """The run that produced no report is exactly the one whose version you need to know."""
    cfg_path = _single_analyzer_config(tmp_path, "snyk", "sast-snyk")
    monkeypatch.setattr(ar.docker_utils, "image_id", lambda image: None)
    monkeypatch.setattr(ar.docker_utils, "image_label", lambda image, label: "snyk 1.1308.3")

    def boom(*args, **kwargs):
        raise RuntimeError("SNYK_TOKEN is not set")

    monkeypatch.setattr(ar, "run_docker", boom)

    launch = _run(tmp_path, cfg_path)
    assert launch["analyzer_outcomes"][0]["status"] == "failed"
    # An unreadable image id is left out instead of being recorded as a known blank.
    assert launch["analyzer_versions"] == [
        {"analyzer": "snyk", "image": "sast-snyk", "tool_version": "snyk 1.1308.3"},
    ]


def test_an_analyzer_nothing_could_be_read_about_is_not_recorded_as_a_version(monkeypatch, tmp_path):
    """A record with no identifying field is noise, not a version."""
    cfg_path = _single_analyzer_config(tmp_path, "legacy", "")
    monkeypatch.setattr(ar.docker_utils, "image_id", lambda image: None)
    monkeypatch.setattr(ar.docker_utils, "image_label", lambda image, label: None)
    monkeypatch.setattr(
        ar,
        "run_docker",
        lambda image, builder_container, args, project_path, output_dir, pipeline_id, env_vars, dockerfile_dir="": None,
    )

    assert _run(tmp_path, cfg_path)["analyzer_versions"] == []


def test_reading_an_image_field_never_fails_the_run_it_describes(monkeypatch):
    """Docker missing or the image absent must degrade to 'unknown', not raise."""
    def no_docker(*args, **kwargs):
        raise OSError("docker: command not found")

    monkeypatch.setattr(ar.docker_utils.subprocess, "run", no_docker)
    assert ar.docker_utils.image_id("sast-semgrep") is None
    assert ar.docker_utils.image_label("sast-semgrep", "aist.tool.version") is None
    assert ar.docker_utils.image_id("") is None


@pytest.mark.parametrize(
    ("report", "status", "result_exists"),
    [("", "missing_result", False), ('{"runs": []}', "success", True)],
)
def test_an_analyzer_that_left_an_empty_report_produced_no_result(
    monkeypatch, tmp_path, caplog, report, status, result_exists,
):
    """An empty report is no report: the run says the analyzer produced nothing, without degrading over it."""
    cfg_path = _single_analyzer_config(tmp_path, "eslint_security", "eslint-security-analyzer")
    monkeypatch.setattr(ar.docker_utils, "image_id", lambda image: None)
    monkeypatch.setattr(ar.docker_utils, "image_label", lambda image, label: None)

    def leave_report(image, builder_container, args, project_path, output_dir, pipeline_id, env_vars, dockerfile_dir=""):
        Path(output_dir, args[2]).write_text(report, encoding="utf-8")

    monkeypatch.setattr(ar, "run_docker", leave_report)

    with caplog.at_level("WARNING", logger=ar.log.name):
        outcome = _run(tmp_path, cfg_path)["analyzer_outcomes"][0]
    assert (outcome["status"], outcome["result_exists"], outcome["degraded"]) == (status, result_exists, False)
    warned = [record.getMessage() for record in caplog.records if "produced no result" in record.getMessage()]
    expected_warning = "Analyzer 'eslint_security' produced no result: eslint_security_result.sarif is missing or empty"
    assert warned == ([] if result_exists else [expected_warning])
