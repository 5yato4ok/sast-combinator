"""Tests for the ``pipeline.docker_utils`` module.

The goal of these tests is to verify the correct construction of
Docker command arguments, environment handling and clean‑up logic
without invoking Docker itself.  The ``subprocess`` and internal
helpers are monkeypatched so that no external commands are executed.
"""

import os
import types

import pytest


def test_get_pipeline_id_sets_and_reuses(monkeypatch):
    """When no pipeline ID is preset in the environment a new one is
    generated, stored in the environment and reused on subsequent
    calls."""
    import pipeline.docker_utils as du

    # Remove any existing ID
    monkeypatch.delenv("PIPELINE_ID", raising=False)
    pid1 = du.get_pipeline_id()
    assert len(pid1) == 8
    assert os.environ["PIPELINE_ID"] == pid1
    # Second call should return the same value
    pid2 = du.get_pipeline_id()
    assert pid2 == pid1
    # If we preset a value it should be returned directly
    monkeypatch.setenv("PIPELINE_ID", "customid")
    assert du.get_pipeline_id() == "customid"


def test_construct_container_name(monkeypatch):
    """The container name should include the pipeline ID and a random
    suffix.  When a pipeline ID is already set in the environment it
    should be used verbatim."""
    import pipeline.docker_utils as du

    # Scenario with no pipeline ID set
    monkeypatch.delenv("PIPELINE_ID", raising=False)
    name, pid = du.construct_container_name("myimg")
    assert pid == os.environ["PIPELINE_ID"]
    assert name.startswith(f"sast_{pid}_myimg_")
    # Scenario with pipeline ID already set
    monkeypatch.setenv("PIPELINE_ID", "abc123")
    name2, pid2 = du.construct_container_name("image")
    assert pid2 == "abc123"
    assert name2.startswith("sast_abc123_image_")


def test_image_exists(monkeypatch):
    """The helper should return True if ``docker images -q`` produces any
    output and False otherwise."""
    import subprocess
    import pipeline.docker_utils as du

    class DummyResult:
        def __init__(self, stdout):
            self.stdout = stdout

    # Simulate a found image
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: DummyResult("abc\n"),
    )
    assert du.image_exists("some-image") is True
    # Simulate no image found
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: DummyResult("\n"),
    )
    assert du.image_exists("other-image") is False


def test_delete_image_if_exist(monkeypatch):
    """``delete_image_if_exist`` should call the removal command only
    when the image actually exists."""
    import pipeline.docker_utils as du
    calls = []
    # Simulate image not present
    monkeypatch.setattr(du, "image_exists", lambda name: False)
    monkeypatch.setattr(du, "run_logged_cmd", lambda cmd, log_addition="": calls.append(cmd))
    du.delete_image_if_exist("img1")
    # No calls made for non‑existent image
    assert calls == []
    # Simulate image present
    monkeypatch.setattr(du, "image_exists", lambda name: True)
    du.delete_image_if_exist("img2")
    # Should have invoked docker image rm
    assert calls[-1][:3] == ["docker", "image", "rm"]


def test_run_container_constructs_command(monkeypatch):
    """Verify that run_container builds the correct command line based on
    provided parameters and calls run_logged_cmd with the assembled
    command."""
    import pipeline.docker_utils as du
    recorded = []
    # Ensure a stable container name and pipeline id
    monkeypatch.setenv("PIPELINE_ID", "pid")
    monkeypatch.setattr(du, "construct_container_name", lambda image: ("cont", "pid"))
    # Capture the command passed to run_logged_cmd
    monkeypatch.setattr(du, "run_logged_cmd", lambda cmd, log_addition="": recorded.append((cmd, log_addition)))
    du.run_container(
        image="myimg",
        volumes_from="base",
        volumes={"/host": "/container"},
        env={"KEY": "VAL"},
        args=["arg"],
    )
    cmd, log_addition = recorded[-1]
    # Command should start with the docker invocation
    assert cmd[:4] == ["docker", "run", "--rm", "--name"]
    # --volumes-from directive
    assert "--volumes-from" in cmd
    # The image name should appear before the arguments
    assert "myimg" in cmd
    assert "arg" in cmd
    # Environment variables are passed with -e
    assert "-e" in cmd
    assert any("KEY=VAL" in part for part in cmd)
    # Volumes mapping is passed with -v
    assert "-v" in cmd
    # The log addition prefixes log lines with the image name
    assert log_addition.startswith("[myimg]")


def test_run_container_name_mismatch(monkeypatch):
    """If a container name is provided but does not include the pipeline
    ID, ``run_container`` should raise an exception."""
    import pipeline.docker_utils as du
    monkeypatch.setenv("PIPELINE_ID", "pid")
    # Use a name that does not contain the pipeline id
    with pytest.raises(Exception):
        du.run_container(image="img", name="bad", volumes_from=None, volumes=None, env=None, args=None)


def test_build_image_logging_and_exit(monkeypatch, caplog):
    """The build helper should log lines based on their content and raise
    an exception for non‑zero exit codes when ``check`` is True."""
    import subprocess
    import pipeline.docker_utils as du
    # Dummy Popen context that yields build output lines
    class DummyPopen:
        def __init__(self, lines, returncode=0):
            self._lines = lines
            self.returncode = returncode
            self.stdout = iter(lines)
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def wait(self):
            return self.returncode
    # Always return our dummy process
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: DummyPopen(["Step 1/2 : downloading", "Step 2/2 : done"], returncode=0))
    # Expect info messages in caplog
    with caplog.at_level("INFO"):
        du.build_image(image_name="testimg", context_dir=".")
        assert any("build testimg" in rec.message for rec in caplog.records)
    # Simulate an error line and a non‑zero return code
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: DummyPopen(["error: failed to fetch"], returncode=1))
    with caplog.at_level("ERROR"):
        with pytest.raises(subprocess.CalledProcessError):
            du.build_image(image_name="errimg", context_dir=".")
        # The error line should have been logged as an error
        assert any("error:" in rec.message.lower() for rec in caplog.records)
    # With check=False a non‑zero returncode should not raise
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: DummyPopen(["failed step"], returncode=1))
    du.build_image(image_name="nocheck", context_dir=".", check=False)


def test_cleanup_pipeline_containers(monkeypatch):
    """Cleaning up pipeline containers should call ``docker rm -f`` for
    every matching container returned by ``docker ps``."""
    import subprocess
    import pipeline.docker_utils as du
    calls = []
    # Simulate docker ps returning two container names
    class DummyCompleted:
        def __init__(self, stdout):
            self.stdout = stdout
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: DummyCompleted("cont1\ncont2\n"),
    )
    # Capture calls to run_logged_cmd instead of actually removing containers
    monkeypatch.setattr(du, "run_logged_cmd", lambda cmd, log_addition="": calls.append(cmd))
    du.cleanup_pipeline_containers("pid")
    # Should call docker rm -f on both containers
    assert calls == [["docker", "rm", "-f", "cont1"], ["docker", "rm", "-f", "cont2"]]