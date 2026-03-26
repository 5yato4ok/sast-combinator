# ruff: noqa: F403,F405
from _real_finding_flow_validation_batch_large_shared import *

@pytest.mark.parametrize(
    (
        "fixture_path",
        "file_path",
        "line_number",
        "function_name",
        "expected_line",
        "reads_subset",
        "trace_symbol",
        "expected_trace_line",
        "expected_definition_line",
        "expected_definition_kind",
        "expected_caller_lines",
    ),
    [
        (
            "nx_maps_ui/auth_guard.tsx",
            "src/components/auth/auth-guard.tsx",
            20,
            "handleOAuthLogin",
            "        router.replace('/errors/something-went-wrong');",
            {"replace", "router"},
            "router",
            9,
            14,
            "variable",
            {50},
        ),
        (
            "nx_maps_ui/auth_guard.tsx",
            "src/components/auth/auth-guard.tsx",
            27,
            "handleOAuthLogin",
            "      logger.warn('[Auth]: Login fail count:', loginFailCount.current);",
            {"current", "logger", "loginFailCount", "warn"},
            "loginFailCount",
            11,
            14,
            "variable",
            {50},
        ),
        (
            "nx_maps_ui/auth_guard.tsx",
            "src/components/auth/auth-guard.tsx",
            35,
            "checkPermissions",
            "      router.replace('/errors/something-went-wrong');",
            {"replace", "router"},
            "router",
            9,
            31,
            "variable",
            {42},
        ),
        (
            "nx_maps_ui/auth_guard.tsx",
            "src/components/auth/auth-guard.tsx",
            42,
            "AuthGuard",
            "      checkPermissions().catch(() => {",
            {"checkPermissions"},
            "checkPermissions",
            31,
            8,
            "function",
            set(),
        ),
        (
            "nx_maps_ui/auth_guard.tsx",
            "src/components/auth/auth-guard.tsx",
            50,
            "AuthGuard",
            "      handleOAuthLogin().catch((error) => {",
            {"handleOAuthLogin"},
            "handleOAuthLogin",
            14,
            8,
            "function",
            set(),
        ),
        (
            "advanced_fov/AdvancedFOVDialog.actions.tsx",
            "src/components/map/edit/AdvancedFOVDialog.tsx",
            18,
            "handleSaveCalibration",
            "      await onSaveCalibration(pointPairs, matrix);",
            {"matrix", "onSaveCalibration", "pointPairs"},
            "matrix",
            13,
            11,
            "variable",
            {50},
        ),
        (
            "advanced_fov/AdvancedFOVDialog.actions.tsx",
            "src/components/map/edit/AdvancedFOVDialog.tsx",
            19,
            "handleSaveCalibration",
            "      logger.debug('Calibration saved successfully');",
            {"debug", "logger"},
            "logger",
            None,
            11,
            "variable",
            {50},
        ),
        (
            "advanced_fov/AdvancedFOVDialog.actions.tsx",
            "src/components/map/edit/AdvancedFOVDialog.tsx",
            24,
            "handleSaveCalibration",
            "      setIsSaving(false);",
            {"setIsSaving"},
            "setIsSaving",
            5,
            11,
            "variable",
            {50},
        ),
        (
            "advanced_fov/AdvancedFOVDialog.actions.tsx",
            "src/components/map/edit/AdvancedFOVDialog.tsx",
            35,
            "handleResetCalibration",
            "      await onDeleteCalibration();",
            {"onDeleteCalibration"},
            "onDeleteCalibration",
            None,
            28,
            "variable",
            {50},
        ),
        (
            "advanced_fov/AdvancedFOVDialog.actions.tsx",
            "src/components/map/edit/AdvancedFOVDialog.tsx",
            36,
            "handleResetCalibration",
            "      logger.debug('Calibration deleted successfully');",
            {"debug", "logger"},
            "logger",
            None,
            28,
            "variable",
            {50},
        ),
        (
            "advanced_fov/AdvancedFOVDialog.actions.tsx",
            "src/components/map/edit/AdvancedFOVDialog.tsx",
            41,
            "handleResetCalibration",
            "      onClose();",
            {"onClose"},
            "onClose",
            None,
            28,
            "variable",
            {50},
        ),
    ],
)
def test_real_findings_additional_auth_guard_and_actions_batch_should_keep_full_flow(
    monkeypatch,
    fixture_path,
    file_path,
    line_number,
    function_name,
    expected_line,
    reads_subset,
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

    classification = mcp_server.classify_file("07734951", file_path)
    extracted = mcp_server.extract_function("07734951", file_path, line_number)
    imports = mcp_server.find_imports("07734951", file_path)
    decorators = mcp_server.find_decorators("07734951", file_path, line_number)
    identifiers = mcp_server.find_identifiers("07734951", file_path, line_number)
    trace = mcp_server.trace_identifier_backward("07734951", file_path, line_number, trace_symbol)
    callers = mcp_server.find_callers("07734951", file_path, function_name)
    definition = mcp_server.find_definition("07734951", function_name)
    route = mcp_server.find_route_to_function("07734951", function_name)

    assert classification["type"] == "production"
    assert imports
    assert decorators == []
    assert extracted["meta"]["code_on_line"] == expected_line
    assert identifiers["language"] == "typescript"
    assert reads_subset.issubset(set(identifiers["reads"]))
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


@pytest.mark.parametrize(
    (
        "fixture_path",
        "file_path",
        "line_number",
        "function_name",
        "expected_line",
        "reads_subset",
        "trace_symbol",
        "expected_trace_line",
        "expected_definition_line",
        "expected_definition_kind",
        "expected_caller_lines",
    ),
    [
        (
            "nx_maps_ui/edit_page.tsx",
            "src/app/map/edit/page.tsx",
            4,
            "EditPage",
            "  const fovData = useMemo(",
            {"buildFovGeoJson", "deviceManagement", "markers", "useMemo"},
            "deviceManagement",
            None,
            3,
            "function",
            set(),
        ),
        (
            "nx_maps_ui/MapSearch.validation.tsx",
            "src/components/map/MapSearch.tsx",
            7,
            "searchValueNow",
            "    const targetSearch = { name: value };",
            {"value"},
            "value",
            None,
            5,
            "variable",
            {23},
        ),
        (
            "nx_maps_ui/useBackgroundWebRTC.ts",
            "src/hooks/map/useBackgroundWebRTC.ts",
            8,
            "disconnectAll",
            "    const clients = Array.from(clientsRef.current.values());",
            {"Array", "clientsRef", "current", "from", "values"},
            "clientsRef",
            4,
            6,
            "variable",
            set(),
        ),
        (
            "nx_maps_ui/geocode-search.ts",
            "src/components/map/search/geocode-search.ts",
            6,
            "geocodeSearch",
            "            const secondaryText = '';",
            set(),
            "secondaryText",
            6,
            3,
            "variable",
            set(),
        ),
        (
            "nx_maps_ui/oauth_page_errors.tsx",
            "src/app/auth/oauth/page.tsx",
            19,
            "handleOAuth",
            "        await handleSystemSelection({ id: 'system-1' });",
            {"handleSystemSelection"},
            "handleSystemSelection",
            7,
            17,
            "variable",
            {26},
        ),
        (
            "nx_maps_ui/oauth_page_errors.tsx",
            "src/app/auth/oauth/page.tsx",
            26,
            "OAuthPage",
            "    handleOAuth();",
            {"handleOAuth"},
            "handleOAuth",
            17,
            4,
            "function",
            set(),
        ),
    ],
)
def test_real_findings_mixed_ts_flow_batch_should_keep_full_flow(
    monkeypatch,
    fixture_path,
    file_path,
    line_number,
    function_name,
    expected_line,
    reads_subset,
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

    classification = mcp_server.classify_file("07734951", file_path)
    extracted = mcp_server.extract_function("07734951", file_path, line_number)
    imports = mcp_server.find_imports("07734951", file_path)
    decorators = mcp_server.find_decorators("07734951", file_path, line_number)
    identifiers = mcp_server.find_identifiers("07734951", file_path, line_number)
    trace = mcp_server.trace_identifier_backward("07734951", file_path, line_number, trace_symbol)
    callers = mcp_server.find_callers("07734951", file_path, function_name)
    definition = mcp_server.find_definition("07734951", function_name)
    route = mcp_server.find_route_to_function("07734951", function_name)

    assert classification["type"] == "production"
    assert imports
    assert decorators == []
    assert extracted["meta"]["code_on_line"] == expected_line
    assert identifiers["language"] == "typescript"
    assert reads_subset.issubset(set(identifiers["reads"]))
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
    assert definition == [item for item in definition if item["file"] == file_path and item["line"] == expected_definition_line and item["kind"] == expected_definition_kind]
    assert route == []


