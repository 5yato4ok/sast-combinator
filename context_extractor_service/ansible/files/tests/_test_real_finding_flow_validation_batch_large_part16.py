# ruff: noqa: F403,F405
from _real_finding_flow_validation_batch_large_shared import *

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
            "nx_maps_ui/oauth_page.tsx",
            "src/app/auth/oauth/page.tsx",
            20,
            "OAuthPage",
            "  const redirectUri = `${config.site.url}/auth/oauth`;",
            {"config", "site", "url"},
            {"redirectUri"},
            "config",
            None,
            10,
            "function",
            set(),
        ),
        (
            "07734951",
            "nx_maps_ui/oauth_page.tsx",
            "src/app/auth/oauth/page.tsx",
            27,
            "extractSystemIdFromReturnUrl",
            "      const mapMatch = returnUrl.match(/\\/map\\?([^&]+)/);",
            {"match", "returnUrl"},
            {"mapMatch"},
            "returnUrl",
            None,
            23,
            "variable",
            {105, 128},
        ),
        (
            "07734951",
            "nx_maps_ui/oauth_page.tsx",
            "src/app/auth/oauth/page.tsx",
            38,
            "extractSystemIdFromReturnUrl",
            "      logger.warn('[OAuth]: Failed to extract systemId from returnUrl:', error);",
            {"error", "logger", "warn"},
            set(),
            "error",
            None,
            23,
            "variable",
            {105, 128},
        ),
        pytest.param(
            "07734951",
            "nx_maps_ui/oauth_page.tsx",
            "src/app/auth/oauth/page.tsx",
            48,
            "getSystems",
            "      timeout: config.requestTimeout,",
            {"AxiosRequestConfig", "accessToken", "cloudHost", "config", "requestTimeout"},
            {"axiosConfig"},
            "config",
            None,
            43,
            "variable",
            set(),
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    "Real OAuthPage regression: extract_function returns the whole AxiosRequestConfig object literal "
                    "instead of the exact timeout property line."
                ),
            ),
        ),
        (
            "07734951",
            "nx_maps_ui/oauth_page.tsx",
            "src/app/auth/oauth/page.tsx",
            63,
            "getSystems",
            "        logger.warn('[OAuth]: Unexpected systems response structure:', data);",
            {"data", "logger", "warn"},
            set(),
            "data",
            53,
            43,
            "variable",
            set(),
        ),
        (
            "07734951",
            "nx_maps_ui/oauth_page.tsx",
            "src/app/auth/oauth/page.tsx",
            78,
            "getTokenForSystem",
            "        logger.warn('[OAuth]: Primary token endpoint failed, trying CDB OAuth2 fallback:', error.response?.data);",
            {"data", "error", "logger", "response", "warn"},
            set(),
            "error",
            None,
            73,
            "variable",
            set(),
        ),
        (
            "69ec5b01",
            "channel_partner_form/ChannelPartnerForm.tsx",
            "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
            13,
            "getRoles",
            "		const rolesResponse = await axios.get(`/channel_partner_roles`);",
            {"axios", "get"},
            {"rolesResponse"},
            "axios",
            None,
            12,
            "variable",
            set(),
        ),
        (
            "69ec5b01",
            "channel_partner_form/ChannelPartnerForm.tsx",
            "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
            17,
            "ChannelPartnerForm",
            "	const { data: rolesData } = useQuery('roles', getRoles);",
            {"getRoles", "useQuery"},
            {"rolesData"},
            "getRoles",
            12,
            4,
            "function",
            set(),
        ),
        (
            "69ec5b01",
            "channel_partner_form/ChannelPartnerForm.tsx",
            "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ChannelPartnerForm.tsx",
            21,
            "changeStage",
            "		if (props.onChangeStage) {",
            {"onChangeStage", "props", "stage"},
            set(),
            "props",
            None,
            20,
            "variable",
            set(),
        ),
        (
            "07734951",
            "nx_maps_ui/edit_page.tsx",
            "src/app/map/edit/page.tsx",
            10,
            "EditPage",
            "    let webpageFromMapId = getWebpageByMapId([], uiState.mapId);",
            {"getWebpageByMapId", "mapId", "uiState"},
            {"webpageFromMapId"},
            "uiState",
            None,
            3,
            "function",
            set(),
        ),
        (
            "07734951",
            "nx_maps_ui/edit_page.tsx",
            "src/app/map/edit/page.tsx",
            13,
            "EditPage",
            '      logger.warn("No webpage found for mapId:", uiState.mapId);',
            {"logger", "mapId", "uiState", "warn"},
            set(),
            "uiState",
            None,
            3,
            "function",
            set(),
        ),
        (
            "07734951",
            "nx_maps_ui/edit_page.tsx",
            "src/app/map/edit/page.tsx",
            26,
            "handleSubmit",
            "      setShowNotEnoughServicesDialog(true);",
            {"setShowNotEnoughServicesDialog"},
            set(),
            "setShowNotEnoughServicesDialog",
            None,
            24,
            "variable",
            set(),
        ),
        (
            "07734951",
            "nx_maps_ui/use-custom-icons.tsx",
            "src/components/dashboard/maps/use-custom-icons.tsx",
            4,
            "useCustomIcons",
            "  icons.forEach((icon) => {",
            {"Image", "forEach", "icon", "icons", "img", "logger", "name", "onerror", "onload"},
            set(),
            "icons",
            None,
            3,
            "function",
            set(),
        ),
        (
            "07734951",
            "nx_maps_ui/use-custom-icons.tsx",
            "src/components/dashboard/maps/use-custom-icons.tsx",
            7,
            "useCustomIcons",
            "    img.onerror = (err) => {",
            {"err", "error", "icon", "img", "logger", "name"},
            {"onerror"},
            "img",
            5,
            3,
            "function",
            set(),
        ),
    ],
)
def test_real_findings_oauth_edit_icons_and_connect_batch_should_keep_full_flow(
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
        "Validated against the real OAuthPage handleSystemSelection shape: find_definition still returns extra "
        "call-site entries for await handleSystemSelection(...) instead of only the variable definition."
    ),
)
def test_real_finding_oauth_handle_system_selection_should_keep_single_definition(monkeypatch, tmp_path):
    source = _fixture_text("nx_maps_ui/oauth_page.tsx")
    file_path = "src/app/auth/oauth/page.tsx"
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "page.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("07734951", file_path)
    extracted = mcp_server.extract_function("07734951", file_path, 86)
    imports = mcp_server.find_imports("07734951", file_path)
    decorators = mcp_server.find_decorators("07734951", file_path, 86)
    identifiers = mcp_server.find_identifiers("07734951", file_path, 86)
    trace = mcp_server.trace_identifier_backward("07734951", file_path, 86, "oauthTokens")
    callers = mcp_server.find_callers("07734951", file_path, "handleSystemSelection")
    definition = mcp_server.find_definition("07734951", "handleSystemSelection")
    route = mcp_server.find_route_to_function("07734951", "handleSystemSelection")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "    const systemTokens = await getTokenForSystem(oauthTokens.refresh_token, system.id);"
    assert "import axios, { AxiosRequestConfig } from 'axios';" in imports
    assert decorators == []
    assert identifiers == {
        "reads": ["getTokenForSystem", "id", "oauthTokens", "refresh_token", "system"],
        "writes": ["systemTokens"],
        "language": "typescript",
    }
    assert trace == []
    assert callers == []
    assert definition == [
        {
            "file": file_path,
            "line": 85,
            "kind": "variable",
            "snippet": definition[0]["snippet"],
        }
    ]
    assert route == []


