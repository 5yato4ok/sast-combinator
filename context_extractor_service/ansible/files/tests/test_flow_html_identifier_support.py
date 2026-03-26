import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server


def _stub_read_source(source: str, file_name: str):
    def _reader(_pipeline_id: str, _file_path: str):
        return source, Path(file_name)

    return _reader


def test_find_identifiers_should_support_inline_script_in_html(monkeypatch):
    source = """\
<script>
document.write('<frame name=\"hmcontent\" src=\"' + defaulttopic + '\" title=\"Content frame\">');
</script>
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "index.html"))

    result = mcp_server.find_identifiers("pipe", "index.html", 2)

    assert "document" in result["reads"]
    assert "write" in result["reads"]
    assert "defaulttopic" in result["reads"]


def test_find_identifiers_should_keep_normal_javascript_inline_expression(monkeypatch):
    source = """\
function render(defaulttopic) {
  document.write('<frame src=\"' + defaulttopic + '\">');
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "index.js"))

    result = mcp_server.find_identifiers("pipe", "index.js", 2)

    assert "document" in result["reads"]
    assert "write" in result["reads"]
    assert "defaulttopic" in result["reads"]
