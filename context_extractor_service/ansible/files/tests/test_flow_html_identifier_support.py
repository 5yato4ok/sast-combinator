import mcp_server
from conftest import _stub_read_source


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
