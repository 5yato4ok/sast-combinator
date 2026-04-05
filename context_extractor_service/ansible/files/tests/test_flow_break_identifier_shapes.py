import mcp_server
from conftest import _stub_read_source


def test_find_identifiers_should_capture_python_function_signature_parameters(monkeypatch):
    source = """\
def change_view(self, request, object_id, form_url='', extra_context=None):
    return True
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "admin.py"))

    result = mcp_server.find_identifiers("pipe", "admin.py", 1)

    assert "change_view" in result["writes"]
    assert "self" in result["writes"]
    assert "request" in result["writes"]
    assert "object_id" in result["writes"]


def test_find_identifiers_should_capture_cpp_member_initializer_identifiers(monkeypatch):
    source = """\
struct P {
    LivePreviewThumbnail* const thumbnailSource = new LivePreviewThumbnail(q);
};
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "live_preview.cpp"))

    result = mcp_server.find_identifiers("pipe", "live_preview.cpp", 2)

    assert "thumbnailSource" in result["writes"]
    assert "q" in result["reads"]  # LivePreviewThumbnail is a type, not a value
    assert "q" in result["reads"]


def test_find_identifiers_should_keep_normal_javascript_assignment_reads_and_writes(monkeypatch):
    source = """\
function buildUrl(base) {
  const nextUrl = base + '/oauth/callback';
  return nextUrl;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.js"))

    result = mcp_server.find_identifiers("pipe", "page.js", 2)

    assert result["writes"] == ["nextUrl"]
    assert "base" in result["reads"]


def test_find_identifiers_should_keep_normal_typescript_declaration_reads_and_writes(monkeypatch):
    source = """\
const channel = new BroadcastChannel(COOKIE_POLICY_CHANNEL)
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "sample.ts"))

    result = mcp_server.find_identifiers("pipe", "sample.ts", 1)

    assert "channel" in result["writes"]
    assert "BroadcastChannel" in result["reads"]
    assert "COOKIE_POLICY_CHANNEL" in result["reads"]


def test_find_identifiers_should_classify_python_with_alias_reads_and_writes(monkeypatch):
    source = """\
def load_config(path):
    with open(path) as handle:
        return handle.read()
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "config.py"))

    result = mcp_server.find_identifiers("pipe", "config.py", 2)

    assert "handle" in result["writes"]
    assert "open" in result["reads"]
    assert "path" in result["reads"]


def test_find_identifiers_should_preserve_cpp_qualified_function_name_reads(monkeypatch):
    source = """\
void ItemGrabber::grabToImage(QQuickItem* item, const QJSValue& callback)
{
    new ItemGrabberWorker(item, callback);
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "item_grabber.cpp"))

    result = mcp_server.find_identifiers("pipe", "item_grabber.cpp", 1)

    assert "grabToImage" in result["writes"]
    assert "ItemGrabber" in result["reads"]
    assert "grabToImage" in result["reads"]
    assert "item" in result["writes"]
    assert "callback" in result["writes"]
