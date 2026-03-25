import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server


def test_read_file_should_return_exact_file_contents(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docker-compose.yml").write_text(
            "services:\n"
            "  web:\n"
            "    image: app\n",
        )

        def _read_source(_pipeline_id: str, file_path: str):
            full = root / file_path
            return full.read_text(), full

        monkeypatch.setattr(mcp_server, "_read_source", _read_source)

        result = mcp_server.read_file("pipe", "docker-compose.yml")

    assert result == "services:\n  web:\n    image: app\n"


def test_search_files_should_return_exact_matching_lines(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "views.py").write_text(
            "def login_view(request):\n"
            "    return True\n",
        )
        (root / "urls.py").write_text(
            "from views import login_view\n"
            "path('/login', login_view)\n",
        )

        monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: root)

        result = mcp_server.search_files("pipe", r"login_view")

    assert sorted(result, key=lambda item: (item["file"], item["line"])) == [
        {"file": "urls.py", "line": 1, "match": "from views import login_view"},
        {"file": "urls.py", "line": 2, "match": "path('/login', login_view)"},
        {"file": "views.py", "line": 1, "match": "def login_view(request):"},
    ]


def test_list_directory_should_return_sorted_entries_with_types(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src").mkdir()
        (root / "README.md").write_text("hello\n")

        monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: root)

        result = mcp_server.list_directory("pipe")

    assert result == [
        {"name": "README.md", "type": "file", "size": 6},
        {"name": "src", "type": "directory"},
    ]


def test_list_directory_should_reject_non_directory_path(monkeypatch):
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("hello\n")

        monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: root)

        result = mcp_server.list_directory("pipe", "README.md")

    assert result == [{"error": "Not a directory: README.md"}]
