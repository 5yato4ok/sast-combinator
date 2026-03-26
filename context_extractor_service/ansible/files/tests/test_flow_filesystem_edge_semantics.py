import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server


def test_search_files_should_report_invalid_regex(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: root)

        result = mcp_server.search_files("pipe", r"(")

    assert result and result[0]["error"].startswith("Invalid regex:")


def test_search_files_should_honor_subdirectory_path(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src").mkdir()
        (root / "docs").mkdir()
        (root / "src" / "views.py").write_text("def login_view(request):\n    return True\n")
        (root / "docs" / "readme.txt").write_text("login_view docs\n")

        monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: root)

        result = mcp_server.search_files("pipe", r"login_view", "src")

    assert result == [{"file": "src/views.py", "line": 1, "match": "def login_view(request):"}]


def test_list_directory_should_reject_path_traversal(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: root)

        result = mcp_server.list_directory("pipe", "../")

    assert result == [{"error": "Path traversal detected"}]


def test_read_file_should_truncate_large_files(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        data = "a" * (1_048_576 + 10)
        (root / "large.txt").write_text(data)

        def _read_source(_pipeline_id: str, file_path: str):
            full = root / file_path
            return full.read_text(), full

        monkeypatch.setattr(mcp_server, "_read_source", _read_source)

        result = mcp_server.read_file("pipe", "large.txt")

    assert result.endswith("\n\n... [truncated at 1 MB]")
    assert len(result) > 1_048_576
