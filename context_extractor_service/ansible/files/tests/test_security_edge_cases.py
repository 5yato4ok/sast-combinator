"""
Tests for security and robustness edge cases found during code review.

Covers:
  - Path traversal prefix-collision guard in _read_source and list_directory
  - search_files with invalid regex
  - _inject_html_script deep traversal (script inside <body>, not top-level)
  - collect_multiline_header with '{' inside string literals and comments
  - debug_ast._find_enclosing_function on deeply nested AST (RecursionError regression)
"""
import multiprocessing
from multiprocessing import Queue
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server
from context_extractor.header import collect_multiline_header
from context_extractor.debug_ast import function_ast_to_string


# ── Path traversal ───────────────────────────────────────────────


def test_read_source_should_reject_path_with_same_prefix_as_source_dir(monkeypatch, tmp_path):
    """
    /var/projects/foo-evil must be rejected when source_dir is /var/projects/foo.
    A simple str.startswith() without trailing '/' would pass this path through.
    """
    source_dir = tmp_path / "project"
    evil_dir = tmp_path / "project-evil"
    source_dir.mkdir()
    evil_dir.mkdir()
    (evil_dir / "secret.txt").write_text("sensitive data")

    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: source_dir)

    with pytest.raises((ValueError, FileNotFoundError)):
        mcp_server._read_source("pipe", "../project-evil/secret.txt")


def test_read_source_should_reject_double_dot_traversal(monkeypatch, tmp_path):
    source_dir = tmp_path / "project"
    outside = tmp_path / "outside"
    source_dir.mkdir()
    outside.mkdir()
    (outside / "creds.txt").write_text("creds")

    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: source_dir)

    with pytest.raises((ValueError, FileNotFoundError)):
        mcp_server._read_source("pipe", "../../outside/creds.txt")


def test_list_directory_should_reject_path_with_same_prefix_as_source_dir(monkeypatch, tmp_path):
    """Same prefix-collision issue as _read_source, but in list_directory."""
    source_dir = tmp_path / "project"
    evil_dir = tmp_path / "project-evil"
    source_dir.mkdir()
    evil_dir.mkdir()
    (evil_dir / "file.txt").write_text("data")

    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: source_dir)

    result = mcp_server.list_directory("pipe", "../project-evil")

    assert result == [{"error": "Path traversal detected"}]


def test_list_directory_should_allow_project_root(monkeypatch, tmp_path):
    """Listing the root of source_dir (path='') must not be rejected by the guard."""
    source_dir = tmp_path / "project"
    source_dir.mkdir()
    (source_dir / "main.py").write_text("x = 1\n")

    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: source_dir)

    result = mcp_server.list_directory("pipe", "")

    names = [e["name"] for e in result]
    assert "main.py" in names


# ── search_files regex safety ────────────────────────────────────


def test_search_files_should_return_error_for_invalid_regex(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)

    result = mcp_server.search_files("pipe", "[unclosed-bracket")

    assert len(result) == 1
    assert "error" in result[0]
    assert "Invalid regex" in result[0]["error"]


def test_search_files_should_return_error_for_unmatched_group(monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)

    result = mcp_server.search_files("pipe", "(?P<name>")

    assert len(result) == 1
    assert "error" in result[0]


def test_search_files_should_return_matches_for_valid_pattern(monkeypatch, tmp_path):
    (tmp_path / "app.py").write_text("cursor.execute(query)\nreturn result\n")

    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pid: tmp_path)

    result = mcp_server.search_files("pipe", r"cursor\.execute")

    assert len(result) == 1
    assert result[0]["line"] == 1
    assert "cursor.execute" in result[0]["match"]


# ── _inject_html_script deep traversal ───────────────────────────


def test_inject_html_script_should_find_script_nested_in_body():
    """
    A <script> block inside <html><body> is NOT a direct child of the document root.
    The old shallow iteration over root_node.children missed it.
    """
    html = """\
<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
<script>
var x = document.getElementById("uid");
x.innerHTML = location.hash;
</script>
</body>
</html>
"""
    from context_extractor.ts_utils import HTML_LANGUAGE
    from mcp_server import _inject_html_script

    # line 7 is: x.innerHTML = location.hash;
    lang, lang_key, source, adjusted_line = _inject_html_script(html, 7, HTML_LANGUAGE, "html")

    assert lang_key == "javascript", "Should have injected JS language"
    assert "innerHTML" in source
    assert adjusted_line >= 1


def test_inject_html_script_should_fall_back_for_html_without_script():
    """Files with no <script> block should return original HTML language unchanged."""
    html = "<html><body><p>Hello</p></body></html>\n"

    from context_extractor.ts_utils import HTML_LANGUAGE
    from mcp_server import _inject_html_script

    lang, lang_key, source, line_number = _inject_html_script(html, 1, HTML_LANGUAGE, "html")

    assert lang_key == "html"
    assert line_number == 1


def test_inject_html_script_should_find_script_in_head():
    """<script> in <head> is also not a direct root child."""
    html = """\
<html>
<head>
<script>
var token = getCookie("csrftoken");
</script>
</head>
</html>
"""
    from context_extractor.ts_utils import HTML_LANGUAGE
    from mcp_server import _inject_html_script

    lang, lang_key, source, adjusted = _inject_html_script(html, 4, HTML_LANGUAGE, "html")

    assert lang_key == "javascript"
    assert "getCookie" in source


# ── header.py brace detection ────────────────────────────────────


def test_collect_multiline_header_should_not_stop_at_brace_in_string_default():
    """
    void f(const std::string s = "{default}")   ← has { only inside a string
    {                                            ← real opening brace
    ...
    """
    lines = [
        'void init(const std::string s = "{default}")',
        "{",
        "    do_something();",
        "}",
    ]
    header, cursor = collect_multiline_header(lines, "cpp", 0, 3)

    # Cursor must point past the '{' line (line index 1), i.e. cursor == 2
    assert cursor == 2
    # Both the signature and the '{' must be in the header
    assert len(header) == 2
    assert "{" in header[1]


def test_collect_multiline_header_should_not_stop_at_brace_in_line_comment():
    """
    void f() // opens { here in comment — not the real brace
    {
    ...
    """
    lines = [
        "void f() // opens { here",
        "{",
        "    return 0;",
        "}",
    ]
    header, cursor = collect_multiline_header(lines, "cpp", 0, 3)

    assert cursor == 2
    assert len(header) == 2


def test_collect_multiline_header_stops_correctly_at_real_brace():
    """Normal case — brace on the same line as the function signature."""
    lines = [
        "void f() {",
        "    return 0;",
        "}",
    ]
    header, cursor = collect_multiline_header(lines, "cpp", 0, 2)

    assert cursor == 1
    assert len(header) == 1
    assert "{" in header[0]


def test_collect_multiline_header_handles_brace_on_separate_line():
    lines = [
        "void f()",
        "{",
        "    return 0;",
        "}",
    ]
    header, cursor = collect_multiline_header(lines, "cpp", 0, 3)

    assert cursor == 2
    assert len(header) == 2


# ── debug_ast iterative DFS ──────────────────────────────────────


def test_find_enclosing_function_should_not_recurse_error_on_deep_nesting():
    """
    Deeply nested lambdas/arrow functions should not cause RecursionError.
    Regression guard for the recursive DFS that was replaced by iterative version.
    """
    # Build a deeply nested Python source with linear growth in source size.
    inner = "x"
    for _ in range(200):
        inner = f"[{inner} for item in range(1)]"
    source = f"def outer():\n    result = {inner}\n    return result\n"

    result = function_ast_to_string(source, "deep.py", 2)

    # Should return a valid AST dump, not raise RecursionError
    assert "outer" in result
    assert "function" in result.lower()


def test_function_ast_to_string_should_finish_on_deep_linear_call_nesting():
    """
    Deep but linearly sized expressions should not hang the AST dump helper.
    This targets real project-shaped inputs where nested calls create a deep AST
    without exploding fixture size before the MCP tool runs.
    """
    expr = "x"
    for _ in range(3000):
        expr = f"f({expr})"
    source = f"def outer():\n    value = {expr}\n    return value\n"

    queue = Queue()

    def _runner() -> None:
        try:
            result = function_ast_to_string(source, "deep.py", 2)
            queue.put(("ok", "outer" in result and "function" in result.lower()))
        except Exception as exc:  # pragma: no cover - surfaced through assertion below
            queue.put(("err", type(exc).__name__, str(exc)))

    # Use fork context to avoid pickling issues with local functions on macOS
    ctx = multiprocessing.get_context("fork")
    proc = ctx.Process(target=_runner)
    proc.start()
    proc.join(5)

    if proc.is_alive():
        proc.terminate()
        proc.join()
        raise AssertionError("function_ast_to_string hung on deep linear nesting")

    assert proc.exitcode == 0
    assert not queue.empty()
    status = queue.get_nowait()
    assert status[0] == "ok", status
    assert status[1] is True


def test_function_ast_to_string_returns_correct_language_header():
    source = """\
def greet(name: str) -> str:
    return f"Hello, {name}"
"""
    result = function_ast_to_string(source, "greet.py", 2)

    assert "lang=python" in result
    assert "greet" in result
