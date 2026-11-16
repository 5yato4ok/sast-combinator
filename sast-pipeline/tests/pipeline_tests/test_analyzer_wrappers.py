"""The analyzer images' own code, run for real: the Horusec wrapper and the ESLint symlink scan.

The Horusec stand-in reproduces what Horusec leaves behind for one situation the wrapper has to
handle, so the test exercises the wrapper's own decisions: whether the analyzer succeeded, and
what the platform's importer is handed. The symlink scan runs on real files.
"""

import json
import os
import resource
import stat
import subprocess
from pathlib import Path

import pytest

DOCKERFILES = Path(__file__).resolve().parents[2] / "Dockerfiles"
HORUSEC_WRAPPER = DOCKERFILES / "horusec" / "analyze.sh"
ESLINT_LINK_SCAN = DOCKERFILES / "eslint_security" / "unresolvable-links.mjs"


def _executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _horusec_report(**overrides) -> dict:
    report = {
        "version": "v2.8.0",
        "status": "success",
        "errors": "",
        "createdAt": "2026-01-01T00:00:00Z",
        "finishedAt": "2026-01-01T00:00:10Z",
        "analysisVulnerabilities": None,
    }
    report.update(overrides)
    return report


def _run_horusec_wrapper(tmp_path: Path, report: dict, *, soft_open_files: int = 256):
    """Run the wrapper on a fresh project; the stand-in writes ``report`` where Horusec writes its own."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    canned = tmp_path / "canned.json"
    canned.write_text(json.dumps(report), encoding="utf-8")
    limit_seen = tmp_path / "limit_seen"
    _executable(bin_dir / "horusec", (
        "#!/bin/sh\n"
        f'ulimit -Sn > "{limit_seen}"\n'
        'while [ "$#" -gt 0 ]; do\n'
        f'  if [ "$1" = "-O" ]; then cp "{canned}" "$2"; fi\n'
        "  shift\n"
        "done\n"
    ))
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("print('hello')\n", encoding="utf-8")
    output = tmp_path / "output"
    hard = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
    result = subprocess.run(
        ["sh", str(HORUSEC_WRAPPER), str(project), str(output), "horusec_result.json"],
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_NOFILE, (soft_open_files, hard)),
        capture_output=True, text=True, check=False,
    )
    return result, output / "horusec_result.json", limit_seen


def test_a_clean_horusec_scan_is_handed_to_the_importer_as_an_empty_finding_list(tmp_path):
    result, report_path, _ = _run_horusec_wrapper(tmp_path, _horusec_report())

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["analysisVulnerabilities"] == []
    assert report["status"] == "success"
    assert report["version"] == "v2.8.0"


def test_horusec_findings_reach_the_importer_unchanged(tmp_path):
    vulnerability = {
        "vulnerabilityID": "6c3a6e44-0000-4000-8000-000000000001",
        "vulnerabilities": {
            "line": "2", "column": "4", "confidence": "MEDIUM", "file": "app.py",
            "code": 'AWS_SECRET = "example"', "details": "Hard-coded secret", "severity": "CRITICAL",
            "language": "Python", "securityTool": "HorusecEngine", "rule_id": "HS-LEAKS-4",
        },
    }
    result, report_path, _ = _run_horusec_wrapper(
        tmp_path, _horusec_report(analysisVulnerabilities=[vulnerability]),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(report_path.read_text(encoding="utf-8"))["analysisVulnerabilities"] == [vulnerability]


def test_a_horusec_scan_its_engine_could_not_finish_fails_the_analyzer_and_leaves_no_report(tmp_path):
    """Horusec exits 0 here; only the report says the scan did not run."""
    engine_error = "{HORUSEC_CLI} Error while running tool HorusecEngine: open /workspace/a.js: too many open files"
    result, report_path, _ = _run_horusec_wrapper(tmp_path, _horusec_report(status="error", errors=engine_error))

    assert result.returncode != 0
    assert not report_path.exists()
    assert "too many open files" in result.stdout


def test_horusec_runs_with_the_open_file_limit_the_container_allows(tmp_path):
    """Containers start with a soft limit far below the hard one, and Horusec never raises it."""
    hard = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
    if hard == resource.RLIM_INFINITY or hard <= 256:
        pytest.skip("needs a finite hard open-file limit above the lowered soft limit")

    result, _, limit_seen = _run_horusec_wrapper(tmp_path, _horusec_report(), soft_open_files=256)

    assert result.returncode == 0, result.stdout + result.stderr
    assert int(limit_seen.read_text(encoding="utf-8")) == hard


def _unresolvable_link_patterns(root: Path) -> list[str]:
    """Run the ESLint image's symlink scan on ``root`` and return the ignore patterns it builds."""
    script = (
        f"import {{ unresolvableLinkPatterns }} from {json.dumps(ESLINT_LINK_SCAN.as_uri())};"
        "process.stdout.write(JSON.stringify(unresolvableLinkPatterns(process.env.SCAN_ROOT)));"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        env={**os.environ, "SCAN_ROOT": str(root)},
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def test_eslint_skips_symlinks_that_resolve_to_nothing_and_only_those(tmp_path):
    """A vendored library shipping `moment.js -> moment.js` used to abort the whole lint."""
    project = tmp_path / "project"
    meteor = project / "static" / "vendor" / "moment" / "meteor"
    meteor.mkdir(parents=True)
    (meteor / "moment.js").symlink_to("moment.js")
    spaced = project / "src" / "with space"
    spaced.mkdir(parents=True)
    (spaced / "dangling.js").symlink_to("missing.js")
    (spaced / "app.js").write_text("eval(input);\n", encoding="utf-8")
    (spaced / "alias.js").symlink_to("app.js")
    (project / "linked-src").symlink_to("src")
    (project / "src" / "a[1].js").symlink_to("gone.js")
    modules = project / "node_modules" / "pkg"
    modules.mkdir(parents=True)
    (modules / "index.js").symlink_to("missing.js")

    assert sorted(_unresolvable_link_patterns(project)) == sorted([
        "static/vendor/moment/meteor/moment.js",
        "src/with space/dangling.js",
        "src/a\\[1\\].js",
    ])


def test_a_hostile_link_name_excludes_only_itself(tmp_path):
    """A name crafted as several paths or as an option stays one literal pattern for its own path."""
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "bad.js").write_text("eval(input);\n", encoding="utf-8")
    (project / "x\nsrc").symlink_to("missing.js")
    (project / "--debug").symlink_to("missing.js")
    (project / "*.js").symlink_to("missing.js")
    (project / "#notes.js").symlink_to("missing.js")

    assert sorted(_unresolvable_link_patterns(project)) == sorted(["x\nsrc", "--debug", "\\*.js", "\\#notes.js"])


def test_eslint_on_a_project_without_broken_symlinks_is_given_no_exclusions(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.js").write_text("eval(input);\n", encoding="utf-8")

    assert _unresolvable_link_patterns(project) == []
