import re
from pathlib import Path

import pytest

CODEQL_DIR = Path(__file__).resolve().parents[2] / "Dockerfiles" / "codeql"

CLI_VERSION_RE = re.compile(r"^ARG CODEQL_VERSION=(\S+)$", re.M)
PACK_ARG_RE = re.compile(r"^ARG CODEQL_QUERIES_VERSION=(\S+)$", re.M)
PACK_DOWNLOAD_RE = re.compile(r"^RUN codeql pack download (\S+)$", re.M)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _language_dirs():
    return sorted(p for p in CODEQL_DIR.iterdir() if (p / "Dockerfile").exists())


def _dockerfile(language_dir):
    return (language_dir / "Dockerfile").read_text(encoding="utf-8")


def test_every_codeql_language_has_an_image():
    languages = {p.name for p in _language_dirs()}
    assert languages == {
        "cpp",
        "csharp",
        "go",
        "java",
        "javascript",
        "python",
        "ruby",
        "swift",
    }


@pytest.mark.parametrize("language_dir", _language_dirs(), ids=lambda p: p.name)
def test_cli_and_query_pack_versions_are_pinned(language_dir):
    content = _dockerfile(language_dir)

    cli_versions = CLI_VERSION_RE.findall(content)
    assert len(cli_versions) == 1
    assert SEMVER_RE.match(cli_versions[0])

    pack_versions = PACK_ARG_RE.findall(content)
    assert len(pack_versions) == 1
    assert SEMVER_RE.match(pack_versions[0])

    downloads = PACK_DOWNLOAD_RE.findall(content)
    assert downloads == [
        f'"codeql/{language_dir.name}-queries@${{CODEQL_QUERIES_VERSION}}"'
    ]


def test_all_images_share_one_cli_version():
    versions = {
        language_dir.name: CLI_VERSION_RE.findall(_dockerfile(language_dir))[0]
        for language_dir in _language_dirs()
    }
    assert len(set(versions.values())) == 1, versions
