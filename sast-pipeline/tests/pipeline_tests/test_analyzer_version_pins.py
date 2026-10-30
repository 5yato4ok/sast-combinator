"""The three scanners that used to install whatever was newest at image build time.

Each is now pinned and stamps the pinned version on the image, so a finding delta between
two pipelines can be attributed to a scanner change instead of to the code.
"""

import re
from pathlib import Path

import pytest

DOCKERFILES_DIR = Path(__file__).resolve().parents[2] / "Dockerfiles"

PINNED_ANALYZERS = {
    "semgrep": {
        "arg": "SEMGREP_VERSION",
        "install": 'pip install --no-cache-dir "semgrep==${SEMGREP_VERSION}"',
    },
    "snyk": {
        "arg": "SNYK_VERSION",
        "install": 'npm install -g "snyk@${SNYK_VERSION}"',
    },
    "bearer": {
        "arg": "BEARER_VERSION",
        "install": "FROM bearer/bearer:${BEARER_VERSION}",
    },
}

TOOL_VERSION_LABEL = "aist.tool.version"
VERSION_RE = re.compile(r"^v?\d+\.\d+\.\d+$")


def _dockerfile(analyzer: str) -> str:
    return (DOCKERFILES_DIR / analyzer / "Dockerfile").read_text(encoding="utf-8")


@pytest.mark.parametrize("analyzer", sorted(PINNED_ANALYZERS))
def test_analyzer_version_is_pinned(analyzer):
    spec = PINNED_ANALYZERS[analyzer]
    content = _dockerfile(analyzer)

    declared = re.findall(rf"^ARG {spec['arg']}=(\S+)$", content, re.M)
    assert declared, f"{analyzer}: no ARG {spec['arg']} default"
    assert VERSION_RE.match(declared[0]), f"{analyzer}: {declared[0]} is not an exact version"

    assert spec["install"] in content, f"{analyzer}: install step does not use ARG {spec['arg']}"


@pytest.mark.parametrize("analyzer", sorted(PINNED_ANALYZERS))
def test_analyzer_stamps_its_version_on_the_image(analyzer):
    spec = PINNED_ANALYZERS[analyzer]
    content = _dockerfile(analyzer)

    labels = re.findall(rf'^LABEL {re.escape(TOOL_VERSION_LABEL)}="([^"]+)"$', content, re.M)
    assert len(labels) == 1, f"{analyzer}: expected exactly one {TOOL_VERSION_LABEL} label"
    assert analyzer in labels[0]
    assert f"${{{spec['arg']}}}" in labels[0], f"{analyzer}: label does not interpolate the pinned version"


@pytest.mark.parametrize("analyzer", sorted(PINNED_ANALYZERS))
def test_no_unpinned_install_remains(analyzer):
    content = _dockerfile(analyzer)
    assert not re.search(r"^\s*FROM .*:latest\s*$", content, re.M)
    assert not re.search(r"pip install[^\n]*\bsemgrep\b(?![=\"])", content)
    assert not re.search(r"npm install -g snyk(?![@\"])", content)
