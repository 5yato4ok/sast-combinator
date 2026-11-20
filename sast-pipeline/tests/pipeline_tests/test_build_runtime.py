"""A build analyzer uses the initialized builder and hands capture artifacts to its image."""

import json
import subprocess
import traceback
from dataclasses import asdict
from pathlib import Path

import pytest
import yaml
from pipeline import analyzer_runner, build_runtime, docker_utils, project_builder
from pipeline.build_configuration import SourceRevision, SourceType
from pipeline.config_utils import AnalyzersConfigHelper


def analyzer(root="/opt/sast-tools/compiler-scan", image="compiler-scan:1"):
    return {
        "name": "compiler_scan", "type": "builder", "image": image,
        "dockerfile_path": "Dockerfiles/compiler_scan", "result_file": "report.sarif",
        "build_runtime": {"root": root, "capture": f"{root}/capture.sh"},
    }


@pytest.fixture
def docker_calls(monkeypatch, tmp_path):
    calls = []
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(build_runtime, "CAPTURE_ROOT", scratch)
    monkeypatch.setattr(docker_utils, "ensure_image", lambda *args, **kwargs: calls.append(("ensure", args)))
    monkeypatch.setattr(docker_utils, "build_source_digest", lambda paths: "source-digest")
    monkeypatch.setattr(docker_utils, "image_id", lambda image: "sha256:resolved")
    monkeypatch.setattr(docker_utils, "run_logged_cmd", lambda cmd, *args: calls.append(("command", cmd)))
    monkeypatch.setattr(docker_utils, "run_container", lambda **kwargs: calls.append(("container", kwargs)))
    return calls


def test_runtime_is_populated_only_when_capture_is_selected(monkeypatch, tmp_path, docker_calls):
    monkeypatch.setenv("SAST_BUILD_COMMAND", "make all")
    with build_runtime.prepare_build_runtimes([analyzer()], "run-one") as runtimes:
        runtime, = runtimes
        assert runtime.mounts == {runtime.volume: "/opt/sast-tools/compiler-scan:ro,nocopy"}
        assert not any(kind == "ensure" for kind, _ in docker_calls)
        monkeypatch.setenv("SAST_BUILD_RUNTIMES", json.dumps([asdict(runtime)]))
        with build_runtime.capture_build(analyzer(), str(tmp_path), "run-one") as captured:
            assert captured.image == "sha256:resolved"
            seed = next(value for kind, value in docker_calls if kind == "container")
            assert seed["image"] == captured.image
            assert seed["entrypoint"] == "/bin/true"
            assert seed["volumes"] == {runtime.volume: runtime.root}
        assert not any(cmd[:3] == ["docker", "volume", "rm"] for kind, cmd in docker_calls if kind == "command")
    assert ("command", ["docker", "volume", "rm", "--force", runtime.volume]) in docker_calls


def test_failed_population_cleans_up_and_preserves_failure(monkeypatch, tmp_path, docker_calls):
    def fail(**kwargs):
        raise subprocess.CalledProcessError(9, ["docker", "run"])

    monkeypatch.setattr(docker_utils, "run_container", fail)
    monkeypatch.setenv("SAST_BUILD_COMMAND", "make all")
    with pytest.raises(subprocess.CalledProcessError):
        with build_runtime.prepare_build_runtimes([analyzer()], "run-failed") as runtimes:
            monkeypatch.setenv("SAST_BUILD_RUNTIMES", json.dumps([asdict(item) for item in runtimes]))
            with build_runtime.capture_build(analyzer(), str(tmp_path), "run-failed"):
                pytest.fail("Failed population must prevent capture")
    assert any(cmd[:3] == ["docker", "volume", "rm"] for kind, cmd in docker_calls if kind == "command")


def test_simultaneous_runs_have_independent_runtime_volumes(docker_calls):
    with build_runtime.prepare_build_runtimes([analyzer()], "same-id") as first:
        with build_runtime.prepare_build_runtimes([analyzer()], "same-id") as second:
            assert first[0].volume != second[0].volume


@pytest.mark.parametrize("root,capture", [
    ("/workspace", "/workspace/capture.sh"),
    ("/opt/sast-tools/tool", "/bin/sh"),
    ("/opt/sast-tools/tool/../other", "/opt/sast-tools/other/capture.sh"),
])
def test_runtime_cannot_replace_project_or_system_paths(root, capture):
    with pytest.raises(ValueError):
        build_runtime.BuildRuntime(root=root, capture=capture)


@pytest.mark.parametrize("failure", [None, "capture", "analysis", "interrupt"])
def test_capture_artifacts_are_temporary_and_report_survives(monkeypatch, tmp_path, docker_calls, failure):
    root = tmp_path / "runtime"
    root.mkdir()
    capture = root / "capture.sh"
    capture.write_text('#!/bin/sh\nset -eu\nprintf "%s" "$PROJECT_TOOLCHAIN" > "$2/toolchain"\n'
                       + ("exit 9\n" if failure == "capture" else ""))
    capture.chmod(0o755)
    config = analyzer()
    spec = build_runtime.BuildRuntime(**config["build_runtime"])
    monkeypatch.setattr(docker_utils, "run_logged_cmd", lambda cmd, *args: subprocess.run([str(capture), *cmd[1:]], check=True))
    prepared = build_runtime.RuntimeMount(root=spec.root, volume="run-tools")
    monkeypatch.setenv("SAST_BUILD_RUNTIMES", json.dumps([asdict(prepared)]))
    monkeypatch.setenv("SAST_BUILD_COMMAND", "make clean all")
    monkeypatch.setenv("PROJECT_TOOLCHAIN", "/compiler/from/init")
    monkeypatch.setenv("NON_COMPILE_PROJECT", "0")
    monkeypatch.setattr(docker_utils, "collect_git_metadata", lambda path: {})
    monkeypatch.setattr(docker_utils, "image_id", lambda image: "sha256:exact")
    monkeypatch.setattr(docker_utils, "image_label", lambda *args: "1")
    observed = []

    def analyze(image, builder_container, args, *positional, **kwargs):
        observed.append((image, args))
        assert Path(args[3], "toolchain").read_text() == "/compiler/from/init"
        if failure == "analysis":
            raise subprocess.CalledProcessError(7, ["analyze"])
        if failure == "interrupt":
            raise KeyboardInterrupt
        Path(args[1], args[2]).write_text('{"runs": []}')

    monkeypatch.setattr(analyzer_runner, "run_docker", analyze)
    config_path = tmp_path / "analyzers.yaml"
    config_path.write_text(yaml.safe_dump({"analyzers": [config]}))
    if failure == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            analyzer_runner.run_selected_analyzers(str(config_path), "run", project_path=str(tmp_path), output_dir=str(tmp_path))
    else:
        analyzer_runner.run_selected_analyzers(str(config_path), "run", project_path=str(tmp_path), output_dir=str(tmp_path))
    assert not list(tmp_path.rglob("toolchain")), "Capture artifacts must be removed after success, failure or cancellation"
    assert not list(tmp_path.glob("build-capture-*")), "Intermediate databases must not be retained with reports"
    assert (tmp_path / "report.sarif").exists() is (failure is None)
    if failure in {"capture", "interrupt"}:
        return
    assert observed[0][0] == "sha256:exact"
    outcome = json.loads((tmp_path / "launch_description.json").read_text())["analyzer_outcomes"][0]
    assert outcome["status"] == ("failed" if failure else "success")


def test_missing_project_build_command_fails_before_capture(monkeypatch, tmp_path):
    monkeypatch.delenv("SAST_BUILD_COMMAND", raising=False)
    with pytest.raises(ValueError, match="SAST_BUILD_COMMAND"):
        with build_runtime.capture_build(analyzer(), str(tmp_path), "run"):
            pytest.fail("Missing command must prevent capture")


def test_resource_limits_are_optional_and_allow_large_workers(monkeypatch):
    calls = []
    monkeypatch.setattr(docker_utils, "run_logged_cmd", lambda cmd, *args, **kwargs: calls.append(cmd))
    limits =docker_utils.ContainerResources(memory="128g", cpus="8")
    docker_utils.run_container(image="builder", pipeline_id="run", resources=limits)
    assert calls[0][calls[0].index("--memory") + 1] == "128g"
    assert calls[0][calls[0].index("--cpus") + 1] == "8"
    docker_utils.run_container(image="builder", pipeline_id="run")
    assert "--memory" not in calls[1]


@pytest.mark.parametrize("base_image", ["", "ubuntu:24.04@sha256:" + "a" * 64])
@pytest.mark.parametrize("source_type", [None, SourceType.GIT_BRANCH, SourceType.GIT_HASH, SourceType.FILE_HASH])
def test_builder_launch_transfers_runtime_identity_mounts_and_resource_policy(
    monkeypatch, tmp_path, docker_calls, base_image, source_type,
):
    monkeypatch.setenv("SAST_BUILDER_MEMORY", "96g")
    monkeypatch.setenv("SAST_ANALYZER_MEMORY", "112g")
    monkeypatch.setenv("SAST_BUILDER_BASE_IMAGE", "ignored-worker-setting")
    script = tmp_path / "init.sh"
    script.write_text("export PROJECT_PATH=/workspace/source\n")
    config = tmp_path / "catalog.yaml"
    config.write_text(yaml.safe_dump({"analyzers": [analyzer() | {"language": ["cpp"]}]}))
    context = tmp_path / "context"
    context.mkdir()
    image_builds = []
    def build(**kwargs):
        image_builds.append(kwargs)
        Path(kwargs["iid_file"]).write_text("sha256:" + "a" * 64)

    monkeypatch.setattr(docker_utils, "build_image", build)
    launched = []

    def run(**kwargs):
        if kwargs.get("entrypoint"):
            return
        launched.append(kwargs)
        output = next(source for source, target in kwargs["volumes"].items() if target == "/shared/output")
        Path(output, "launch_description.json").write_text(json.dumps({"project_path": "/workspace/source"}))

    monkeypatch.setattr(docker_utils, "run_container", run)
    archive = tmp_path / "extracted"
    archive.mkdir()
    (archive / "source.cpp").write_text("int main() { return 0; }\n")
    revision = SourceRevision(version="release", type=source_type, extracted_root=str(archive))
    project_builder.configure_project_run_analyses(
        str(script), str(tmp_path / "output"), ["cpp"], AnalyzersConfigHelper(str(config)),
        "Dockerfile", str(context), "builder-test", project_path=str(tmp_path / "workspace"),
        additional_env={"SAST_BUILDER_MEMORY": "128g", "SAST_BUILDER_CPUS": "16"},
        base_image=base_image, version=revision,
    )
    if source_type == SourceType.FILE_HASH:
        assert (tmp_path / "workspace" / "source.cpp").read_text() == (archive / "source.cpp").read_text()
    call, = launched
    if source_type in {SourceType.GIT_BRANCH, SourceType.GIT_HASH}:
        assert call["env"]["PROJECT_VERSION"] == "release"
    assert call["image"] == "sha256:" + "a" * 64
    runtime, = json.loads(call["env"]["SAST_BUILD_RUNTIMES"])
    assert call["volumes"][runtime["volume"]] == f'{runtime["root"]}:ro,nocopy'
    assert not any(kind == "ensure" for kind, _ in docker_calls)
    assert call["resources"] == docker_utils.ContainerResources(memory="128g", cpus="16")
    assert call["env"]["SAST_ANALYZER_MEMORY"] == "112g"
    assert image_builds[0]["build_args"].get("BUILDER_BASE_IMAGE", "") == base_image


def test_capture_failure_is_visible_and_other_analyzers_still_run(monkeypatch, tmp_path):
    config = tmp_path / "catalog.yaml"
    config.write_text(yaml.safe_dump({"analyzers": [
        analyzer() | {"required_result": True},
        {"name": "source_scan", "image": "source-scan", "result_file": "source.sarif"},
    ]}))
    monkeypatch.setenv("NON_COMPILE_PROJECT", "0")
    monkeypatch.delenv("SAST_BUILD_COMMAND", raising=False)
    monkeypatch.setattr(docker_utils, "collect_git_metadata", lambda path: {})
    monkeypatch.setattr(docker_utils, "image_id", lambda image: image)
    monkeypatch.setattr(docker_utils, "image_label", lambda *args: "1")
    monkeypatch.setattr(analyzer_runner, "run_docker", lambda *args, **kwargs: (tmp_path / "source.sarif").write_text('{"runs": []}'))
    analyzer_runner.run_selected_analyzers(str(config), "run", project_path=str(tmp_path), output_dir=str(tmp_path))
    outcomes = json.loads((tmp_path / "launch_description.json").read_text())["analyzer_outcomes"]
    assert [(outcome["name"], outcome["status"]) for outcome in outcomes] == [
        ("compiler_scan", "failed"), ("source_scan", "success"),
    ]
    assert outcomes[0]["degraded"] is True


def test_failed_authenticated_analyzer_does_not_disclose_its_token(monkeypatch, tmp_path, caplog):
    secret = "sentinel-token-must-never-appear-in-outcomes"
    config = tmp_path / "catalog.yaml"
    config.write_text(yaml.safe_dump({"analyzers": [{
        "name": "authenticated_scan", "image": "authenticated-scan", "env": ["SCANNER_TOKEN"],
    }]}))
    monkeypatch.setenv("SCANNER_TOKEN", secret)
    monkeypatch.setattr(docker_utils, "collect_git_metadata", lambda path: {})
    monkeypatch.setattr(docker_utils, "image_id", lambda image: image)
    monkeypatch.setattr(docker_utils, "image_label", lambda *args: "1")
    monkeypatch.setattr(docker_utils, "ensure_image", lambda *args, **kwargs: None)

    def fail(cmd, *args, **kwargs):
        assert Path(cmd[cmd.index("--env-file") + 1]).read_text() == f"SCANNER_TOKEN={secret}\n"
        assert not any(secret in arg for arg in cmd)
        raise subprocess.CalledProcessError(17, cmd)

    monkeypatch.setattr(docker_utils, "run_logged_cmd", fail)
    analyzer_runner.run_selected_analyzers(str(config), "run", project_path=str(tmp_path), output_dir=str(tmp_path))
    launch = (tmp_path / "launch_description.json").read_text()
    assert secret not in launch
    assert secret not in caplog.text
    outcome, = json.loads(launch)["analyzer_outcomes"]
    assert outcome["status"] == "failed"
    assert "status 17" in outcome["messages"][0]["text"]


def test_container_failure_preserves_exit_status_for_provider_recovery(monkeypatch):
    secret = "sentinel-private-value"
    def fail(cmd, *args, **kwargs):
        raise subprocess.CalledProcessError(23, cmd)

    monkeypatch.setattr(docker_utils, "run_logged_cmd", fail)
    with pytest.raises(subprocess.CalledProcessError) as error:
        docker_utils.run_container(image="provider", pipeline_id="run", env={"TOKEN": secret})
    assert error.value.returncode == 23
    assert secret not in str(error.value)
    assert secret not in "".join(traceback.format_exception(error.value))
