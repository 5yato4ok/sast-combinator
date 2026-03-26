# ruff: noqa: F403,F405
from _real_finding_flow_validation_batch_large_shared import *

@pytest.mark.xfail(
    strict=True,
    reason=(
        "Real StatusForm regression: find_definition still fails to return the arrow-component definition for StatusForm."
    ),
)
def test_real_finding_status_form_should_keep_arrow_component_definition(monkeypatch, tmp_path):
    source = _fixture_text("nx_connect/status_form/StatusForm.tsx")
    file_path = "app/(dashboard)/status/StatusForm.tsx"
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "StatusForm.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, 6)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, 6)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, 6)
    trace = mcp_server.trace_identifier_backward("69ec5b01", file_path, 6, "hasUnsavedChanges")
    callers = mcp_server.find_callers("69ec5b01", file_path, "StatusForm")
    definition = mcp_server.find_definition("69ec5b01", "StatusForm")
    route = mcp_server.find_route_to_function("69ec5b01", "StatusForm")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "\tconst hasUnsavedChanges = () => true;"
    assert imports == [
        "import { useEditEntityFormRef } from '@/app/(dashboard)/components/EntityInformation/hooks/useEditEntityFormRef';"
    ]
    assert decorators == []
    assert identifiers == {"reads": [], "writes": ["hasUnsavedChanges"], "language": "typescript"}
    assert trace == [{"line": 6, "code": "const hasUnsavedChanges = () => true;", "writes": ["hasUnsavedChanges"], "reads": []}]
    assert callers == []
    assert definition == [
        {
            "file": file_path,
            "line": 3,
            "kind": "variable",
            "snippet": definition[0]["snippet"],
        }
    ]
    assert route == []


