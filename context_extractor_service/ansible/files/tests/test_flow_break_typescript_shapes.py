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


def test_extract_function_should_keep_exact_line_inside_multiline_destructured_signature():
    source = """\
const MapSearch = ({
  systems,
  getLoadedDevices,
  mapCenter,
  deviceCount = 0,
}) => {
  return systems.length;
}
"""

    result = extract_function_from_source(source, "MapSearch.tsx", 2, 200)

    assert result["meta"]["code_on_line"] == "  systems,"


def test_find_identifiers_should_capture_bindings_inside_multiline_destructured_signature(monkeypatch):
    source = """\
const MapSearch = ({
  systems,
  getLoadedDevices,
  mapCenter,
  deviceCount = 0,
}) => {
  return systems.length;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "MapSearch.tsx"))

    result = mcp_server.find_identifiers("pipe", "MapSearch.tsx", 2)

    assert "systems" in result["writes"]


def test_extract_function_should_keep_exact_line_for_normal_typescript_statement():
    source = """\
function loadMap() {
  const systems = getSystems();
  return systems.length;
}
"""

    result = extract_function_from_source(source, "map.ts", 2, 200)

    assert result["meta"]["code_on_line"] == "  const systems = getSystems();"


def test_find_identifiers_should_capture_normal_tsx_expression_reads(monkeypatch):
    source = """\
export default function OAuthDebugPage() {
  const nextUrl = "/oauth/callback";
  return <a href={nextUrl}>Continue</a>;
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))

    result = mcp_server.find_identifiers("pipe", "page.tsx", 3)

    assert "nextUrl" in result["reads"]
