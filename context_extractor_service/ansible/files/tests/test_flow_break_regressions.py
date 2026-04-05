import mcp_server
from conftest import _stub_read_source


def test_find_identifiers_should_not_treat_window_as_write_on_javascript_location_redirect(monkeypatch):
    source = """\
function bindCustomizationSwitch() {
  $('#id_customization_view').change(function(event) {
    var queryParams = new URLSearchParams(window.location.search);
    queryParams.set('customization', this.value);
    window.location.href = window.location.pathname + '?' + queryParams.toString();
  });
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "menuChange.js"))

    result = mcp_server.find_identifiers("pipe", "menuChange.js", 5)

    assert "window" not in result["writes"]
    assert "pathname" in result["reads"]
    assert "queryParams" in result["reads"]
    assert "toString" in result["reads"]


def test_find_identifiers_should_capture_single_line_jsx_callback_reads(monkeypatch):
    source = """\
function MapPage() {
  return (
    <IconButton onClick={() => dispatch(clearSiteError())} size="small" />
  );
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))

    result = mcp_server.find_identifiers("pipe", "page.tsx", 3)

    assert "dispatch" in result["reads"]
    assert "clearSiteError" in result["reads"]
