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


def test_extract_function_should_keep_inline_jsx_callback_context():
    source = """\
function Page() {
  return <Button onClick={() => {
    router.push('/x')
  }}>Go</Button>
}
"""

    result = extract_function_from_source(source, "page.tsx", 2, 200)

    assert "onClick={() => {" in result["meta"]["code_on_line"]


def test_find_identifiers_should_capture_inline_jsx_callback_reads(monkeypatch):
    source = """\
function Page() {
  return <Button onClick={() => {
    router.push('/x')
  }}>Go</Button>
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))

    result = mcp_server.find_identifiers("pipe", "page.tsx", 2)

    assert "router" in result["reads"]
    assert "push" in result["reads"]


def test_extract_function_should_keep_normal_tsx_return_line_context():
    source = """\
export default function OAuthDebugPage() {
  const nextUrl = "/oauth/callback";
  return <a href={nextUrl}>Continue</a>;
}
"""

    result = extract_function_from_source(source, "page.tsx", 3, 200)

    assert result["meta"]["code_on_line"] == "  return <a href={nextUrl}>Continue</a>;"


def test_find_identifiers_should_keep_normal_tsx_href_reads(monkeypatch):
    source = """\
export default function OAuthDebugPage() {
  const nextUrl = "/oauth/callback";
  return <a href={nextUrl}>Continue</a>;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))

    result = mcp_server.find_identifiers("pipe", "page.tsx", 3)

    assert "nextUrl" in result["reads"]
