import pytest, sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def _stub_read_source(source: str, file_name: str):
    """Return a drop-in replacement for mcp_server._read_source that serves fixed content."""
    def _reader(_pipeline_id: str, _file_path: str):
        return source, Path(file_name)
    return _reader


def pytest_sessionstart(session):
    missing = []
    for mod in ["tree_sitter_cpp", "tree_sitter_python", "tree_sitter_javascript", "tree_sitter_java", "tree_sitter_c_sharp",
            "tree_sitter_kotlin", "tree_sitter_go", "tree_sitter_ruby"]:
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    if missing:
        pytest.skip(f"Missing dependencies: {', '.join(missing)}", allow_module_level=True)
