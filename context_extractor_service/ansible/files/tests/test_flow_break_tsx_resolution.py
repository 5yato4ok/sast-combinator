import mcp_server
from conftest import _stub_read_source


def test_find_identifiers_should_not_return_no_node_for_single_line_tsx_callback(monkeypatch):
    source = """\
function MapPage() {
  return <IconButton onClick={() => dispatch(clearSiteError())} size="small" />;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))

    result = mcp_server.find_identifiers("pipe", "page.tsx", 2)

    assert "error" not in result
    assert "dispatch" in result["reads"]
    assert "clearSiteError" in result["reads"]


def test_find_identifiers_should_support_tsx_anchor_expression(monkeypatch):
    source = """\
export default function OAuthDebugPage() {
  const nextUrl = "/oauth/callback";
  return <a href={nextUrl}>Continue</a>;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))

    result = mcp_server.find_identifiers("pipe", "page.tsx", 3)

    assert "nextUrl" in result["reads"]


def test_find_identifiers_should_keep_normal_typescript_template_literal_inputs(monkeypatch):
    source = """\
class UriService {
  changePort(newPort: string): void {
    window.location.replace(`${window.location.hostname}:${newPort}`);
  }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "uri.service.ts"))

    result = mcp_server.find_identifiers("pipe", "uri.service.ts", 3)

    assert "window" in result["reads"]
    assert "newPort" in result["reads"]


def test_find_identifiers_should_keep_normal_tsx_href_expression(monkeypatch):
    source = """\
export default function OAuthDebugPage() {
  const nextUrl = "/oauth/callback";
  return <a href={nextUrl}>Continue</a>;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))

    result = mcp_server.find_identifiers("pipe", "page.tsx", 3)

    assert "nextUrl" in result["reads"]
