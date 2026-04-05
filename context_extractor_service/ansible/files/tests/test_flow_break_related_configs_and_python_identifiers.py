from pathlib import Path
from tempfile import TemporaryDirectory

import mcp_server
from conftest import _stub_read_source
from context_extractor.config_analysis import find_related_configs


def test_find_related_configs_should_ignore_plain_text_mentions_in_shell_scripts():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "Dockerfile").write_text("FROM python:3.11\n")
        (root / "scripts").mkdir()
        (root / "scripts" / "build_distribution.sh").write_text(
            "#!/usr/bin/env bash\n"
            "echo 'Dockerfile must exist before build'\n",
        )

        related = find_related_configs(root, "Dockerfile")

    assert related == []


def test_find_related_configs_should_keep_real_compose_relationship():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "Dockerfile").write_text("FROM python:3.11\n")
        (root / "docker-compose.yml").write_text(
            "services:\n"
            "  web:\n"
            "    build:\n"
            "      context: .\n"
            "      dockerfile: Dockerfile\n",
        )

        related = find_related_configs(root, "Dockerfile")

    assert related == [{"file": "docker-compose.yml", "relationship": "referenced_by_compose"}]


def test_find_identifiers_should_capture_python_with_open_reads_and_writes(monkeypatch):
    source = """\
def load_template(scss_file):
    with open(scss_file) as f:
        return f.read()
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "extract_brand_core_values.py"))

    result = mcp_server.find_identifiers("pipe", "extract_brand_core_values.py", 2)

    assert "open" in result["reads"]
    assert "scss_file" in result["reads"]
    assert "f" in result["writes"]


def test_find_identifiers_should_keep_normal_python_assignment_reads_and_writes(monkeypatch):
    source = """\
def build_url(return_url):
    oauth_url = create_oauth_url(return_url)
    return oauth_url
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "oauth_handler.py"))

    result = mcp_server.find_identifiers("pipe", "oauth_handler.py", 2)

    assert result["writes"] == ["oauth_url"]
    assert "create_oauth_url" in result["reads"]
    assert "return_url" in result["reads"]
