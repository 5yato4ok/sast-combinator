"""Exercise the shell adapter with a recording CLI and a real project build command."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

WRAPPERS = Path(__file__).resolve().parents[2] / "Dockerfiles" / "codeql" / "cpp"


@pytest.fixture
def cli(tmp_path):
    tool = tmp_path / "tool"
    tool.mkdir()
    for name in ("capture.sh", "build.sh"):
        shutil.copy2(WRAPPERS / name, tool / name)
    fake = tool / "codeql"
    fake.write_text('''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys
args = sys.argv[1:]
with open(os.environ["CALLS"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if args[:2] == ["database", "init"]:
    pathlib.Path(args[2]).mkdir()
if args[:2] == ["database", "trace-command"]:
    work = args[args.index("--working-dir") + 1]
    sys.exit(subprocess.run(args[args.index("--") + 1:], cwd=work).returncode)
if args[:2] == ["database", "finalize"]:
    sys.exit(int(os.environ.get("FINALIZE_EXIT", "0")))
if args[:2] == ["database", "analyze"]:
    pathlib.Path(args[args.index("--output") + 1]).write_text('{"runs": []}')
''')
    fake.chmod(0o755)
    project = tmp_path / "source with spaces"
    project.mkdir()
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    env = os.environ | {
        "PATH": f"{tool}:{os.environ['PATH']}", "CALLS": str(tmp_path / "calls.jsonl"),
        "SAST_BUILD_COMMAND": 'printf "%s" "$FROM_INIT" > built.txt', "FROM_INIT": "prepared toolchain",
        "CODEQL_QUERIES_VERSION": "1.9.2",
    }
    return tool, project, artifacts, env


def test_capture_build_then_finalize_and_analyze_in_separate_phase(cli):
    tool, project, artifacts, env = cli
    subprocess.run(["bash", str(tool / "capture.sh"), str(project), str(artifacts)], env=env, check=True)
    assert (project / "built.txt").read_text() == "prepared toolchain"
    calls = [json.loads(line) for line in Path(env["CALLS"]).read_text().splitlines()]
    assert [call[:2] for call in calls] == [["database", "init"], ["database", "trace-command"]]
    subprocess.run(["bash", str(WRAPPERS / "analyze.sh"), str(project), str(artifacts), "result.sarif", str(artifacts)], env=env, check=True)
    calls = [json.loads(line) for line in Path(env["CALLS"]).read_text().splitlines()]
    assert [call[:2] for call in calls[-2:]] == [["database", "finalize"], ["database", "analyze"]]
    assert "codeql/cpp-queries@1.9.2:codeql-suites/cpp-security-extended.qls" in calls[-1]
    assert (artifacts / "result.sarif").exists()


def test_failed_build_is_not_reported_as_success(cli):
    tool, project, artifacts, env = cli
    env["SAST_BUILD_COMMAND"] = "exit 17"
    result = subprocess.run(["bash", str(tool / "capture.sh"), str(project), str(artifacts)], env=env)
    assert result.returncode == 17


def test_failed_finalization_does_not_publish_a_report(cli):
    _, project, artifacts, env = cli
    env["FINALIZE_EXIT"] = "32"
    result = subprocess.run(["bash", str(WRAPPERS / "analyze.sh"), str(project), str(artifacts), "result.sarif", str(artifacts)], env=env)
    assert result.returncode == 32
    assert not (artifacts / "result.sarif").exists()
