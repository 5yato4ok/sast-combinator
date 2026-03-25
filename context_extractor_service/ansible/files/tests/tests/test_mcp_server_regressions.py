import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server
from context_extractor.project_analysis import trace_identifier_backward


def _stub_read_source(source: str, file_name: str):
    def _reader(_pipeline_id: str, _file_path: str):
        return source, Path(file_name)

    return _reader


def test_find_identifiers_should_support_tsx_files(monkeypatch):
    source = """\
export default function OAuthDebugPage() {
    const nextUrl = "/oauth/callback";

    return <a href={nextUrl}>Continue</a>;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))

    result = mcp_server.find_identifiers("pipe", "src/app/debug/oauth/page.tsx", 4)

    assert "nextUrl" in result["reads"]


def test_find_identifiers_should_capture_go_assignment_reads_and_writes(monkeypatch):
    source = """\
func f(data []byte) {
    hash := md5.Sum(data)
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "site_info_reader.go"))

    result = mcp_server.find_identifiers("pipe", "site_info_reader.go", 2)

    assert "hash" in result["writes"]
    assert "md5" in result["reads"]
    assert "data" in result["reads"]


def test_find_identifiers_should_capture_typescript_template_literal_inputs(monkeypatch):
    source = """\
class UriService {
    changePort(newPort: string): void {
        window.location.replace(
            `${window.location.protocol}//${window.location.hostname}:${newPort}/${window.location.hash}`,
        );
    }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "uri.service.ts"))

    result = mcp_server.find_identifiers("pipe", "uri.service.ts", 3)

    assert "window" in result["reads"]
    assert "newPort" in result["reads"]


def test_find_identifiers_should_capture_typescript_declaration_reads_and_writes(monkeypatch):
    source = "const channel = new BroadcastChannel(COOKIE_POLICY_CHANNEL)\n"
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "sample.ts"))

    result = mcp_server.find_identifiers("pipe", "sample.ts", 1)

    assert "channel" in result["writes"]
    assert "BroadcastChannel" in result["reads"]
    assert "COOKIE_POLICY_CHANNEL" in result["reads"]


def test_find_identifiers_should_capture_javascript_template_literal_identifiers(monkeypatch):
    source = 'const stateLabel = `<a href="${reviewUrl}">${state}</a>`;\n'
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "sample.js"))

    result = mcp_server.find_identifiers("pipe", "sample.js", 1)

    assert "stateLabel" in result["writes"]
    assert "reviewUrl" in result["reads"]
    assert "state" in result["reads"]


def test_trace_identifier_backward_should_keep_template_literal_reads():
    source = """\
class UriService {
    changePort(newPort: string): void {
        const url = `${newPort}`
        window.location.replace(url)
    }
}
"""
    chain = trace_identifier_backward(source, Path("uri.service.ts"), 4, "url")

    assert chain
    assert "newPort" in chain[0]["reads"]
