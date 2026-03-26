# ruff: noqa: F403,F405
from _real_finding_flow_validation_batch_large_shared import *

@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real OAuthPage finding shape: find_definition(handleSystemSelection) still "
        "returns an extra false-positive function entry for the call site instead of only the actual definition."
    ),
)
def test_real_finding_oauth_set_error_should_keep_exact_definition_set(monkeypatch, tmp_path):
    source = _fixture_text("nx_maps_ui/oauth_page_errors.tsx")
    file_path = "src/app/auth/oauth/page.tsx"
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("07734951", file_path)
    extracted = mcp_server.extract_function("07734951", file_path, 12)
    imports = mcp_server.find_imports("07734951", file_path)
    decorators = mcp_server.find_decorators("07734951", file_path, 12)
    identifiers = mcp_server.find_identifiers("07734951", file_path, 12)
    trace = mcp_server.trace_identifier_backward("07734951", file_path, 12, "setError")
    callers = mcp_server.find_callers("07734951", file_path, "handleSystemSelection")
    definition = mcp_server.find_definition("07734951", "handleSystemSelection")
    route = mcp_server.find_route_to_function("07734951", "handleSystemSelection")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "      setError('select');"
    assert imports == [
        "import React, { useEffect, useState } from 'react';",
        "import { logger } from '@/lib/logging/default-logger';",
    ]
    assert decorators == []
    assert identifiers == {"reads": ["setError"], "writes": [], "language": "typescript"}
    assert trace == [
        {
            "line": 5,
            "code": "const [error, setError] = useState<string | null>(null);",
            "writes": ["setError"],
            "reads": ["useState"],
        }
    ]
    assert callers == []
    assert definition == [
        {
            "file": file_path,
            "line": 7,
            "kind": "variable",
            "snippet": definition[0]["snippet"],
        }
    ]
    assert route == []


@pytest.mark.parametrize(
    (
        "pipeline_id",
        "fixture_path",
        "file_path",
        "line_number",
        "function_name",
        "expected_line",
        "reads_subset",
        "expected_writes_subset",
        "trace_symbol",
        "expected_trace_line",
        "expected_definition_line",
        "expected_definition_kind",
        "expected_caller_lines",
    ),
    [
        (
            "07734951",
            "nx_maps_ui/use-custom-icons.tsx",
            "src/components/dashboard/maps/use-custom-icons.tsx",
            5,
            "useCustomIcons",
            "    const img = new Image();",
            {"Image"},
            {"img"},
            "img",
            5,
            3,
            "function",
            set(),
        ),
        (
            "07734951",
            "nx_maps_ui/use-custom-icons.tsx",
            "src/components/dashboard/maps/use-custom-icons.tsx",
            6,
            "useCustomIcons",
            "    img.onload = () => {};",
            {"img"},
            {"onload"},
            "img",
            5,
            3,
            "function",
            set(),
        ),
        (
            "07734951",
            "nx_maps_ui/layout.tsx",
            "src/app/layout.tsx",
            17,
            "RootLayout",
            "        <AuthGuard>",
            {"AuthGuard", "children"},
            set(),
            "children",
            None,
            7,
            "function",
            set(),
        ),
        (
            "69ec5b01",
            "channel_partner_form/ChannelPartnerForm.tsx",
            "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
            10,
            "ChannelPartnerForm",
            "	const [isCreatingChannelPartner, setIsCreatingChannelPartner] = useState(false);",
            {"useState"},
            {"isCreatingChannelPartner", "setIsCreatingChannelPartner"},
            "useState",
            None,
            4,
            "function",
            set(),
        ),
        (
            "07734951",
            "nx_maps_ui/oauth_page.tsx",
            "src/app/auth/oauth/page.tsx",
            15,
            "OAuthPage",
            "  const [tokens, setTokens] = useState(null);",
            {"useState"},
            {"setTokens", "tokens"},
            "setTokens",
            15,
            10,
            "function",
            set(),
        ),
        (
            "07734951",
            "nx_maps_ui/oauth_page.tsx",
            "src/app/auth/oauth/page.tsx",
            116,
            "handleOAuth",
            "          window.location.href = searchParams.get('returnUrl') || '/';",
            {"get", "location", "searchParams", "window"},
            {"href"},
            "searchParams",
            12,
            91,
            "variable",
            {140},
        ),
    ],
)
def test_real_findings_more_ts_and_connect_batch_should_keep_full_flow(
    monkeypatch,
    pipeline_id,
    fixture_path,
    file_path,
    line_number,
    function_name,
    expected_line,
    reads_subset,
    expected_writes_subset,
    trace_symbol,
    expected_trace_line,
    expected_definition_line,
    expected_definition_kind,
    expected_caller_lines,
    tmp_path,
):
    source = _fixture_text(fixture_path)
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, Path(file_path).name))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file(pipeline_id, file_path)
    extracted = mcp_server.extract_function(pipeline_id, file_path, line_number)
    imports = mcp_server.find_imports(pipeline_id, file_path)
    decorators = mcp_server.find_decorators(pipeline_id, file_path, line_number)
    identifiers = mcp_server.find_identifiers(pipeline_id, file_path, line_number)
    trace = mcp_server.trace_identifier_backward(pipeline_id, file_path, line_number, trace_symbol)
    callers = mcp_server.find_callers(pipeline_id, file_path, function_name)
    definition = mcp_server.find_definition(pipeline_id, function_name)
    route = mcp_server.find_route_to_function(pipeline_id, function_name)

    assert classification["type"] == "production"
    assert imports
    assert decorators == []
    assert extracted["meta"]["code_on_line"] == expected_line
    assert identifiers["language"] == "typescript"
    assert reads_subset.issubset(set(identifiers["reads"]))
    assert expected_writes_subset.issubset(set(identifiers["writes"]))
    if expected_trace_line is None:
        assert trace == []
    else:
        assert trace
        assert trace[0]["line"] == expected_trace_line
    if expected_caller_lines:
        assert callers
        assert expected_caller_lines.issubset({item["line"] for item in callers if item["file"] == file_path})
    else:
        assert callers == []
    assert any(
        item["file"] == file_path and item["line"] == expected_definition_line and item["kind"] == expected_definition_kind
        for item in definition
    )
    assert route == []


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real ChannelPartnerForm deleteUser finding shape: extract_function still expands the "
        "axios.delete().then().catch chain instead of returning the exact .catch((error) => { line."
    ),
)
def test_real_finding_channel_partner_delete_catch_should_keep_exact_chain_line(monkeypatch, tmp_path):
    source = _fixture_text("channel_partner_form/ChannelPartnerForm.tsx")
    file_path = "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx"
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "ChannelPartnerForm.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, 30)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, 30)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, 30)
    trace = mcp_server.trace_identifier_backward("69ec5b01", file_path, 30, "newSubCpId")
    callers = mcp_server.find_callers("69ec5b01", file_path, "deleteUser")
    definition = mcp_server.find_definition("69ec5b01", "deleteUser")
    route = mcp_server.find_route_to_function("69ec5b01", "deleteUser")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "\t\t\t.catch((error) => {"
    assert imports == [
        "import axios from '@/app/axiosInstance';",
        "import { useContext, useState } from 'react';",
    ]
    assert decorators == []
    assert identifiers["language"] == "typescript"
    assert {"axios", "catch", "console", "delete", "email", "error", "newSubCpId", "then"} == set(identifiers["reads"])
    assert identifiers["writes"] == []
    assert trace == []
    assert callers == []
    assert definition == [
        {
            "file": file_path,
            "line": 26,
            "kind": "variable",
            "snippet": definition[0]["snippet"],
        }
    ]
    assert route == []


