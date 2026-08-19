"""Tests for the ``pipeline.docker_utils`` module.

The goal of these tests is to verify the correct construction of
Docker command arguments, environment handling and clean‑up logic
without invoking Docker itself.  The ``subprocess`` and internal
helpers are monkeypatched so that no external commands are executed.
"""

import os
import re
import types

import pytest


def test_get_pipeline_id_returns_a_fresh_short_id():
    """Each call mints its own short id; callers that need a stable one pass it around."""
    import pipeline.docker_utils as du

    first = du.get_pipeline_id()
    second = du.get_pipeline_id()
    assert len(first) == 8
    assert first != second


@pytest.mark.parametrize(
    "image",
    [
        "sast-semgrep",
        "acme/sast-semgrep",
        "aist-dast-connector:v2",
        "registry.example.com:5000/team/aist-dast-connector:v2",
    ],
)
def test_container_name_is_valid_for_every_catalog_image(image):
    """
    A container name must satisfy dockerd for every image a catalog may declare.

    dockerd accepts ``[a-zA-Z0-9][a-zA-Z0-9_.-]*``; a tagged image previously produced a name
    containing ':' and the run failed before the connector ever started. DAST is the only
    catalog entry carrying a tag, which is why nothing else surfaced this.
    """
    import pipeline.docker_utils as du

    name = du.construct_container_name(image, "pipe1234")

    assert re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name), name


def test_container_name_carries_the_pipeline_id_for_cleanup():
    """Cleanup finds containers by pipeline id, so the name must keep it verbatim."""
    import pipeline.docker_utils as du

    assert "pipe1234" in du.construct_container_name("aist-dast-connector:v2", "pipe1234")


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
    monkeypatch.setattr(du, "run_logged_cmd", lambda cmd, log_addition="": recorded.append((cmd, log_addition)))
    du.run_container(
        image="myimg",
        pipeline_id="pid",
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


def test_run_container_overrides_the_image_user_only_when_asked(monkeypatch):
    """A step that owns its mounts can pin the identity the container runs as."""
    import pipeline.docker_utils as du
    recorded = []
    monkeypatch.setattr(du, "run_logged_cmd", lambda cmd, log_addition="": recorded.append(cmd))

    du.run_container(image="img", pipeline_id="pid", user="1000:1000")
    du.run_container(image="img", pipeline_id="pid")

    with_user, without_user = recorded
    assert with_user[with_user.index("--user") + 1] == "1000:1000"
    assert "--user" not in without_user


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        ("1001:1001", (1001, 1001)),
        # Docker takes the group from inside the image, so leave it alone rather than guess.
        ("1001", (1001, -1)),
        ("", None),
        # A name would have to be resolved against the image's own /etc/passwd.
        ("appuser", None),
    ],
)
def test_image_runtime_user_reports_only_an_identity_it_can_act_on(monkeypatch, declared, expected):
    import pipeline.docker_utils as du

    monkeypatch.setattr(
        du.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(returncode=0, stdout=f"{declared}\n", stderr=""),
    )

    assert du.image_runtime_user("img") == expected


def test_image_runtime_user_is_none_for_an_image_that_is_not_there(monkeypatch):
    import pipeline.docker_utils as du

    monkeypatch.setattr(
        du.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(returncode=1, stdout="", stderr="No such image"),
    )

    assert du.image_runtime_user("img") is None


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
        def wait(self, timeout=None):
            # The real build is capped so a hung one cannot hold the calling worker forever.
            self.wait_timeout = timeout
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
    # Each container is stopped before it is removed: a live connector needs the chance to write
    # its recovery/outcome files on shutdown, and the removal still has to happen so a leftover
    # name cannot block the next run under the same pipeline id.
    assert calls == [
        ["docker", "stop", "cont1"],
        ["docker", "rm", "-f", "cont1"],
        ["docker", "stop", "cont2"],
        ["docker", "rm", "-f", "cont2"],
    ]

def test_run_pipeline_container_builds_a_missing_image_before_running(monkeypatch, tmp_path):
    """
    Every containerized step must be able to bring up its own image.

    SAST analyzers and the VPN sidecar each did this in their own helper; the DAST connector
    called run_container directly and failed because nothing in the runtime builds its image --
    the compose file never declares it.
    """
    import pipeline.docker_utils as du

    built: list[tuple[str, str]] = []
    ran: list[dict] = []
    monkeypatch.setattr(du, "image_exists", lambda image: False)
    monkeypatch.setattr(du, "build_image", lambda **kwargs: built.append((kwargs["image_name"], kwargs["context_dir"])))
    monkeypatch.setattr(du, "run_container", lambda **kwargs: ran.append(kwargs))
    monkeypatch.setattr(du, "HOST_SHARED_ROOT", tmp_path)
    workspace = tmp_path / "run"
    workspace.mkdir()
    context = tmp_path / "Dockerfiles" / "dast_connector"
    context.mkdir(parents=True)

    du.run_pipeline_container(
        image="aist-dast-connector:v2",
        dockerfile_dir=str(context),
        pipeline_id="pipe1234",
        volumes={str(workspace): "/work"},
    )

    assert built == [("aist-dast-connector:v2", str(context))]
    assert ran and ran[0]["image"] == "aist-dast-connector:v2"


def test_run_pipeline_container_skips_the_build_when_the_image_is_present(monkeypatch, tmp_path):
    import pipeline.docker_utils as du

    built: list = []
    monkeypatch.setattr(du, "image_exists", lambda image: True)
    monkeypatch.setattr(du, "build_image", lambda **kwargs: built.append(kwargs))
    monkeypatch.setattr(du, "run_container", lambda **kwargs: None)
    monkeypatch.setattr(du, "HOST_SHARED_ROOT", tmp_path)

    du.run_pipeline_container(
        image="sast-semgrep",
        dockerfile_dir="/app/Dockerfiles/semgrep",
        pipeline_id="pipe1234",
        volumes={str(tmp_path): "/work"},
    )

    assert built == []


def test_run_pipeline_container_refuses_a_path_the_daemon_cannot_read(monkeypatch, tmp_path):
    """
    Bind-mount sources are resolved by the daemon on the host, not inside this container.

    A workspace under the container's private /tmp mounts as an empty directory, so the
    connector would start and find neither its input nor its token. Refuse it by name instead.
    """
    import pipeline.docker_utils as du

    monkeypatch.setattr(du, "image_exists", lambda image: True)
    monkeypatch.setattr(du, "run_container", lambda **kwargs: pytest.fail("must not run"))
    monkeypatch.setattr(du, "HOST_SHARED_ROOT", tmp_path / "shared")

    with pytest.raises(du.UnsharedWorkspaceError):
        du.run_pipeline_container(
            image="aist-dast-connector:v2",
            dockerfile_dir="/app/Dockerfiles/dast_connector",
            pipeline_id="pipe1234",
            volumes={"/tmp/private-workspace": "/work"},
        )


def test_pipeline_workspace_is_created_under_the_shared_root(monkeypatch, tmp_path):
    import pipeline.docker_utils as du

    monkeypatch.setattr(du, "HOST_SHARED_ROOT", tmp_path / "shared")

    with du.pipeline_workspace("pipe1234") as workspace:
        assert workspace.is_dir()
        assert str(workspace).startswith(str(tmp_path / "shared"))
        marker = workspace / "input.json"
        marker.write_text("{}", encoding="utf-8")

    assert not workspace.exists()


# Image-ensuring lives here, next to the run helper that depends on it: a step cannot run an
# image that nothing builds, and the runtime deployment declares none of them.
def test_ensure_image_skips_when_image_exists(monkeypatch, tmp_path):
    import pipeline.docker_utils as du

    _ensure = du.ensure_image
    """When the image already exists, ``ensure_image`` must not invoke the build helper."""

    calls = []
    # Pretend the image already exists
    monkeypatch.setattr(du, "image_exists", lambda name: True)
    # Record any attempted build calls
    monkeypatch.setattr(du, "build_image", lambda *args, **kwargs: calls.append((args, kwargs)))

    _ensure("img", str(tmp_path))
    # build_image must not have been called
    assert calls == []


def test_ensure_image_builds_with_and_without_log_level(monkeypatch, tmp_path):
    import pipeline.docker_utils as du

    _ensure = du.ensure_image
    """When the image does not exist the helper should call ``build_image``
    with appropriate arguments and include the LOG_LEVEL environment
    variable as a build argument if present."""

    captured = []

    def fake_build_image(
        *,
        image_name,
        context_dir,
        dockerfile=None,
        build_args=None,
        labels=None,
        check=True,
        default_log_level="DEBUG",
        timeout=None,
    ):
        # Capture the build invocation for later inspection
        captured.append({
            "image_name": image_name,
            "context_dir": context_dir,
            "dockerfile": dockerfile,
            "build_args": build_args,
            "check": check,
            "default_log_level": default_log_level,
        })

    monkeypatch.setattr(du, "image_exists", lambda name: False)
    monkeypatch.setattr(du, "build_image", fake_build_image)
    ctx1 = tmp_path / "ctx1"
    ctx1.mkdir()
    ctx2 = tmp_path / "ctx2"
    ctx2.mkdir()
    # First call with no LOG_LEVEL set
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    _ensure("img1", str(ctx1))
    assert captured[-1]["image_name"] == "img1"
    assert captured[-1]["context_dir"] == str(ctx1)
    # build_args is either None or empty when LOG_LEVEL is not defined
    assert captured[-1]["build_args"] in (None, {})
    # Now call with a LOG_LEVEL defined
    captured.clear()
    monkeypatch.setenv("LOG_LEVEL", "TRACE")
    _ensure("img2", str(ctx2))
    assert captured[-1]["image_name"] == "img2"
    assert captured[-1]["context_dir"] == str(ctx2)
    # build_args should contain the propagated LOG_LEVEL
    assert captured[-1]["build_args"] == {"LOG_LEVEL": "TRACE"}




def test_catalog_build_context_resolves_against_the_package_root(monkeypatch, tmp_path):
    """
    A catalog path is relative to this package root — the one anchor every caller shares.

    Inside the builder image that root is /app, so `Dockerfiles/<name>` lands where the image
    copies them; from the Celery worker the same entry resolves under the platform project.
    Neither caller needs a path spelled for the other.
    """
    import pipeline.docker_utils as du

    package_root = tmp_path / "sast-pipeline"
    (package_root / "Dockerfiles" / "dast_connector").mkdir(parents=True)
    monkeypatch.setattr(du, "PACKAGE_ROOT", package_root)

    resolved = du.resolve_build_context("Dockerfiles/dast_connector")

    assert resolved == str(package_root / "Dockerfiles" / "dast_connector")


def test_an_absolute_build_context_is_honoured_as_given(monkeypatch, tmp_path):
    """A caller supplying its own absolute context is not second-guessed."""
    import pipeline.docker_utils as du

    context = tmp_path / "own" / "context"
    context.mkdir(parents=True)
    monkeypatch.setattr(du, "PACKAGE_ROOT", tmp_path / "elsewhere")

    assert du.resolve_build_context(str(context)) == str(context)


def test_a_build_context_that_exists_nowhere_is_named_in_the_error(monkeypatch, tmp_path):
    import pipeline.docker_utils as du

    monkeypatch.setattr(du, "PACKAGE_ROOT", tmp_path)

    with pytest.raises(du.BuildContextNotFoundError) as caught:
        du.resolve_build_context("Dockerfiles/missing_analyzer")

    assert "missing_analyzer" in str(caught.value)


# A stale tag is the one failure the "does the image exist" question cannot see: `:v2` names the
# protocol revision, so the first build on a host owns the tag forever, and the packaged connector
# then parses input files written by code it does not match.
def test_ensure_image_rebuilds_a_tag_that_no_longer_matches_its_sources(monkeypatch, tmp_path):
    import pipeline.docker_utils as du

    captured = []
    monkeypatch.setattr(du, "image_exists", lambda name: True)
    monkeypatch.setattr(du, "image_label", lambda image, label: "digest-of-an-older-revision")
    monkeypatch.setattr(du, "build_image", lambda **kwargs: captured.append(kwargs))

    du.ensure_image("aist-dast-connector:v2", str(tmp_path), source_digest="digest-of-this-revision")

    assert len(captured) == 1
    # The rebuild has to record what it was built from, or the next call rebuilds it again.
    assert captured[0]["labels"] == {du.SOURCE_DIGEST_LABEL: "digest-of-this-revision"}


def test_ensure_image_keeps_a_tag_built_from_the_same_sources(monkeypatch, tmp_path):
    import pipeline.docker_utils as du

    monkeypatch.setattr(du, "image_exists", lambda name: True)
    monkeypatch.setattr(du, "image_label", lambda image, label: "digest-of-this-revision")
    monkeypatch.setattr(du, "build_image", lambda **kwargs: pytest.fail("must not rebuild"))

    du.ensure_image("aist-dast-connector:v2", str(tmp_path), source_digest="digest-of-this-revision")


def test_ensure_image_rebuilds_an_image_that_records_no_sources(monkeypatch, tmp_path):
    """Every image built before the digest existed -- including one a deploy script built."""
    import pipeline.docker_utils as du

    captured = []
    monkeypatch.setattr(du, "image_exists", lambda name: True)
    monkeypatch.setattr(du, "image_label", lambda image, label: None)
    monkeypatch.setattr(du, "build_image", lambda **kwargs: captured.append(kwargs))

    du.ensure_image("aist-dast-connector:v2", str(tmp_path), source_digest="digest-of-this-revision")

    assert len(captured) == 1


def test_build_source_digest_follows_every_file_the_dockerfile_copies(monkeypatch, tmp_path):
    """A directory is digested whole, because that is what a COPY of it takes."""
    import pipeline.docker_utils as du

    package_root = tmp_path / "sast-pipeline"
    (package_root / "pipeline" / "dast").mkdir(parents=True)
    (package_root / "pipeline" / "__init__.py").write_text("", encoding="utf-8")
    contracts = package_root / "pipeline" / "dast" / "contracts.py"
    contracts.write_text("FIELDS = {'stop_requested'}\n", encoding="utf-8")
    monkeypatch.setattr(du, "PACKAGE_ROOT", package_root)
    paths = ("pipeline/__init__.py", "pipeline/dast")

    before = du.build_source_digest(paths)
    contracts.write_text("FIELDS = {'stop_requested', 'harvest_only'}\n", encoding="utf-8")

    assert du.build_source_digest(paths) != before
    # Order of the declared entries is not part of the identity of a revision.
    assert du.build_source_digest(tuple(reversed(paths))) == du.build_source_digest(paths)


def test_build_source_digest_ignores_bytecode_caches(monkeypatch, tmp_path):
    """__pycache__ is not in the image, and it appears whenever the worker imports the package."""
    import pipeline.docker_utils as du

    package_root = tmp_path / "sast-pipeline"
    cache = package_root / "pipeline" / "dast" / "__pycache__"
    cache.mkdir(parents=True)
    (package_root / "pipeline" / "dast" / "connector.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(du, "PACKAGE_ROOT", package_root)

    before = du.build_source_digest(("pipeline/dast",))
    (cache / "connector.cpython-313.pyc").write_bytes(b"compiled")

    assert du.build_source_digest(("pipeline/dast",)) == before


def test_build_image_records_the_labels_it_is_given(monkeypatch):
    import subprocess
    import pipeline.docker_utils as du

    commands = []

    class DummyPopen:
        def __init__(self, cmd):
            commands.append(cmd)
            self.stdout = iter(())
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kwargs: DummyPopen(cmd))

    du.build_image(image_name="img", context_dir=".", labels={du.SOURCE_DIGEST_LABEL: "abc123"})

    assert commands == [["docker", "build", "--label", f"{du.SOURCE_DIGEST_LABEL}=abc123", "-t", "img", "."]]
