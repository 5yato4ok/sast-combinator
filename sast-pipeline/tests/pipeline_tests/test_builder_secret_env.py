"""Secret builder variables reach the builder only, and their values never reach a log."""

import json
import logging
from pathlib import Path

import pytest
import yaml
from pipeline import docker_utils, project_builder
from pipeline.config_utils import AnalyzersConfigHelper

SECRET = "conan-remote-password-7f3a"


@pytest.fixture
def relay(monkeypatch, caplog):
    """Run a shell script whose environment holds the secret and return the relayed log lines."""
    monkeypatch.setenv("CONAN_PASSWORD", SECRET)

    def run(script):
        with caplog.at_level(logging.DEBUG, logger=docker_utils.log.name):
            docker_utils.run_logged_cmd(["sh", "-c", script], "[builder]", redact=[SECRET])
        return [record.getMessage() for record in caplog.records]

    return run


def test_a_value_the_init_script_prints_is_masked(relay, caplog):
    lines = relay('echo "conan remote login acme -p $CONAN_PASSWORD"; echo "$CONAN_PASSWORD" >&2')

    assert "[builder] conan remote login acme -p ***" in lines
    assert "[builder] ***" in lines
    assert SECRET not in caplog.text


def test_a_value_written_in_pieces_is_masked(relay):
    lines = relay('printf "token=conan-remote-"; sleep 0.3; printf "password-7f3a done\\n"')

    assert lines == ["[builder] token=*** done"]


def test_output_without_a_final_line_break_is_still_relayed(relay):
    lines = relay('printf "first\\nlast $CONAN_PASSWORD"')

    assert lines == ["[builder] first", "[builder] last ***"]


class _RecordedPopen:
    """Stands in for ``subprocess.Popen``: records how ``docker`` would be started, then stops."""

    calls: list = []

    def __init__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs, Path(cmd[cmd.index("--env-file") + 1]).read_text()))
        raise RuntimeError("recorded")


def test_container_variables_never_change_how_the_worker_starts_docker(monkeypatch):
    _RecordedPopen.calls = []
    monkeypatch.setattr(docker_utils.subprocess, "Popen", _RecordedPopen)

    with pytest.raises(RuntimeError, match="recorded"):
        docker_utils.run_container(
            image="builder", pipeline_id="run1",
            env={"PATH": "/opt/tool/bin", "DOCKER_HOST": "tcp://elsewhere:2375", "CONAN_PASSWORD": SECRET},
        )

    (cmd, kwargs, env_text), = _RecordedPopen.calls
    assert "env" not in kwargs
    assert cmd[0] == "docker"
    assert env_text == f"PATH=/opt/tool/bin\nDOCKER_HOST=tcp://elsewhere:2375\nCONAN_PASSWORD={SECRET}\n"
    assert not any(SECRET in part for part in cmd)


@pytest.mark.parametrize(("env", "message"), [
    ({"CONAN_KEY": "-----BEGIN KEY-----\nabc"}, "CONAN_KEY holds a line break"),
    ({"A=B": "x"}, "name 'A=B' cannot be passed"),
    ({"#COMMENT": "x"}, "name '#COMMENT' cannot be passed"),
])
def test_a_variable_a_container_cannot_receive_is_refused_before_docker_runs(monkeypatch, env, message):
    started = []
    monkeypatch.setattr(docker_utils, "run_logged_cmd", lambda *args, **kwargs: started.append(args))

    with pytest.raises(ValueError, match=message):
        docker_utils.run_container(image="builder", pipeline_id="run1", env=env)

    assert started == []


@pytest.fixture
def builder_launch(monkeypatch, tmp_path):
    """Run ``configure_project_run_analyses`` against a recorded Docker, returning the builder launches."""
    script = tmp_path / "init.sh"
    script.write_text("conan install .\n")
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(yaml.safe_dump({"analyzers": [{"name": "scan", "image": "scan", "result_file": "r.sarif"}]}))
    context = tmp_path / "context"
    context.mkdir()
    builds, launches = [], []

    def build(**kwargs):
        builds.append(kwargs)
        Path(kwargs["iid_file"]).write_text("sha256:" + "b" * 64)

    def run(**kwargs):
        launches.append(kwargs)
        output = next(source for source, target in kwargs["volumes"].items() if target == "/shared/output")
        Path(output, "launch_description.json").write_text(json.dumps({"project_path": "/workspace"}))

    monkeypatch.setattr(docker_utils, "build_image", build)
    monkeypatch.setattr(docker_utils, "run_container", run)

    def launch(**kwargs):
        project_builder.configure_project_run_analyses(
            str(script), str(tmp_path / "output"), ["cpp"], AnalyzersConfigHelper(str(catalog)),
            "Dockerfile", str(context), "run1", image_name="builder-test",
            project_path=str(tmp_path / "workspace"), **kwargs,
        )
        return builds, launches

    return launch


def test_secret_variables_reach_the_builder_and_are_masked(builder_launch):
    builds, launches = builder_launch(
        additional_env={"REPO_URL": "https://example.invalid/repo.git"},
        secret_env={"CONAN_LOGIN_USERNAME_ACME": "ci-user", "CONAN_PASSWORD_ACME": SECRET},
    )

    builder, = launches
    assert builder["env"]["CONAN_LOGIN_USERNAME_ACME"] == "ci-user"
    assert builder["env"]["CONAN_PASSWORD_ACME"] == SECRET
    assert builder["env"]["REPO_URL"] == "https://example.invalid/repo.git"
    assert sorted(builder["redact"]) == sorted(["ci-user", SECRET])
    assert SECRET not in json.dumps(builds[0]["build_args"])


@pytest.mark.parametrize(("name", "additional_env"), [
    ("PIPELINE_ID", {}),
    ("SAST_BUILDER_MEMORY", {}),
    ("JOBS", {}),
    ("REPO_URL", {"REPO_URL": "https://example.invalid/repo.git"}),
])
def test_a_secret_variable_cannot_redefine_the_builder_or_launch_environment(builder_launch, name, additional_env):
    with pytest.raises(ValueError, match=f"redefines {name}"):
        builder_launch(additional_env=additional_env, secret_env={name: SECRET})
