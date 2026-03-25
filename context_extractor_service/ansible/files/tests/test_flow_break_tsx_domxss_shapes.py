import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server
from context_extractor.extract import extract_function_from_source


def _stub_read_source(source: str, file_name: str):
    def _reader(_pipeline_id: str, _file_path: str):
        return source, Path(file_name)

    return _reader


def test_find_identifiers_should_capture_dangerously_set_inner_html_reads(monkeypatch):
    source = """\
function GlobalSearchBar() {
  return <span className={styles.commandKey} dangerouslySetInnerHTML={{ __html: getCommandKeySymbol() }} />
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "GlobalSearchBar.tsx"))

    result = mcp_server.find_identifiers("pipe", "GlobalSearchBar.tsx", 2)

    assert "styles" in result["reads"]
    assert "getCommandKeySymbol" in result["reads"]


def test_extract_function_should_keep_dangerously_set_inner_html_line_context():
    source = """\
function GlobalSearchBar() {
  return <span className={styles.commandKey} dangerouslySetInnerHTML={{ __html: getCommandKeySymbol() }} />
}
"""

    result = extract_function_from_source(source, "GlobalSearchBar.tsx", 2, 200)

    assert result["meta"]["code_on_line"] == (
        "  return <span className={styles.commandKey} dangerouslySetInnerHTML={{ __html: getCommandKeySymbol() }} />"
    )


def test_find_identifiers_should_keep_normal_js_template_literal_reads(monkeypatch):
    source = 'const stateLabel = `<a href="${reviewUrl}">${state}</a>`;\n'
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "sample.js"))

    result = mcp_server.find_identifiers("pipe", "sample.js", 1)

    assert "stateLabel" in result["writes"]
    assert "reviewUrl" in result["reads"]
    assert "state" in result["reads"]


def test_extract_function_should_keep_normal_single_line_jsx_return():
    source = """\
function AlertTitle() {
  return <span className={styles.alertTitle}>{children}</span>;
}
"""

    result = extract_function_from_source(source, "Alert.tsx", 2, 200)

    assert result["meta"]["code_on_line"] == "  return <span className={styles.alertTitle}>{children}</span>;"
