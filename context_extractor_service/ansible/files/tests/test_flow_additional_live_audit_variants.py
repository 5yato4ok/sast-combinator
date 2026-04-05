import mcp_server
from conftest import _stub_read_source
from context_extractor.extract import extract_function_from_source


def test_extract_function_should_keep_exact_line_for_typescript_object_property():
    source = """\
function loadBrandConfig() {
  try {
    return require('./brand.json');
  } catch (error) {
    return {
      customization: 'default',
      cloudHost: 'nxvms.com',
      mapsName: 'NxMaps',
      supportLink: 'https://support.networkoptix.com',
    };
  }
}
"""

    result = extract_function_from_source(source, "config.ts", 8, 200)

    assert result["meta"]["code_on_line"] == "      mapsName: 'NxMaps',"


def test_find_identifiers_should_support_inline_script_html_line(monkeypatch):
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


def test_extract_function_should_keep_exact_line_for_normal_typescript_object_property():
    source = """\
function loadBrandConfig() {
  return {
    mapsName: 'NxMaps',
    supportLink: 'https://support.networkoptix.com',
  };
}
"""

    result = extract_function_from_source(source, "config.ts", 3, 200)

    assert result["meta"]["code_on_line"] == "    mapsName: 'NxMaps',"


def test_find_identifiers_should_keep_normal_javascript_member_expression(monkeypatch):
    source = """\
function render(defaulttopic) {
  document.write(defaulttopic);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "sample.js"))

    result = mcp_server.find_identifiers("pipe", "sample.js", 2)

    assert "document" in result["reads"]
    assert "write" in result["reads"]
    assert "defaulttopic" in result["reads"]
