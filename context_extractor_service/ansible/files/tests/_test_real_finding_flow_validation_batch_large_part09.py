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
    ),
    [
        pytest.param(
            "nx_maps_ui/use-custom-icons.tsx",
            "src/components/dashboard/maps/use-custom-icons.tsx",
            7,
            "useCustomIcons",
            "    img.onerror = (err) => {",
            {"err", "icon", "logger", "name"},
            "icon",
            None,
            3,
            "function",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real icon-loading regression: extract_function snaps to the img.onerror header instead of the logger.error finding line.",
            ),
        ),
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
        ),
        pytest.param(
            "nx_maps_ui/edit_page.tsx",
            "src/app/map/edit/page.tsx",
            10,
            "EditPage",
            "    let webpageFromMapId = getWebpageByMapId([], uiState.mapId);",
            {"debug", "logger", "storedBackground"},
            "storedBackground",
            None,
            3,
            "function",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real map-edit regression: extract_function returns the preceding webpageFromMapId assignment instead of the storedBackground logger line.",
            ),
        ),
        pytest.param(
            "nx_maps_ui/edit_page.tsx",
            "src/app/map/edit/page.tsx",
            18,
            "EditPage",
            "  const isOldImageMap = true;",
            {"location", "tmpMarker"},
            "tmpMarker",
            None,
            3,
            "function",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real map-edit regression: extract_function snaps to the isOldImageMap declaration instead of the tmpMarker.location assignment.",
            ),
        ),
        pytest.param(
            "nx_maps_ui/edit_page.tsx",
            "src/app/map/edit/page.tsx",
            25,
            "handleSubmit",
            "    if (serviceCount.isOverCapacity) {",
            {"isOverCapacity", "serviceCount"},
            "serviceCount",
            None,
            22,
            "variable",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real submit-flow regression: extract_function loses the if guard line entirely and returns an empty code_on_line.",
            ),
        ),
    ],
)
def test_real_findings_additional_nx_maps_ui_should_keep_full_code_flow(
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
    assert extracted["meta"]["code_on_line"] == expected_line
    assert imports
    assert decorators == []
    assert identifiers["language"] == "typescript"
    assert reads_subset.issubset(set(identifiers["reads"]))
    assert isinstance(trace, list)
    assert any(
        item["file"] == file_path and item["line"] == expected_definition_line and item["kind"] == expected_definition_kind
        for item in definition
    )
    assert isinstance(callers, list)
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
        pytest.param(
            "nx_maps_ui/oauth_page_errors.tsx",
            "src/app/auth/oauth/page.tsx",
            11,
            "handleSystemSelection",
            "      logger.error('[OAuth]: Error selecting system', err);",
            {"err", "error", "logger"},
            "err",
            None,
            6,
            "variable",
            {18},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real OAuth helper-flow regression: find_callers misses handleSystemSelection local invocation.",
            ),
        ),
        pytest.param(
            "nx_maps_ui/oauth_page_errors.tsx",
            "src/app/auth/oauth/page.tsx",
            20,
            "handleOAuth",
            "      } catch (err) {",
            {"err", "error", "logger"},
            "err",
            None,
            16,
            "variable",
            {24},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real OAuth flow regression: extract_function snaps to the catch header instead of the logger.error line.",
            ),
        ),
        pytest.param(
            "nx_maps_ui/auth_guard_navigation.tsx",
            "src/components/auth/auth-guard.tsx",
            16,
            "AuthGuard",
            "      handleOAuthLogin().catch((error) => {",
            {"error", "logger"},
            "error",
            None,
            5,
            "function",
            set(),
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real auth-guard regression: extract_function snaps to the promise catch header instead of the navigation logger.error line.",
            ),
        ),
        pytest.param(
            "nx_maps_ui/MapSearch.validation.tsx",
            "src/components/map/MapSearch.tsx",
            10,
            "searchValueNow",
            "    if (typeof lng !== 'number' || typeof lat !== 'number' || isNaN(lng) || isNaN(lat)) {",
            {"error", "lat", "lng", "logger"},
            "lng",
            7,
            4,
            "variable",
            {21},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real MapSearch regression: the coordinate-validation logger line is not recovered with the expected trace/caller flow.",
            ),
        ),
        pytest.param(
            "nx_maps_ui/MapSearch.validation.tsx",
            "src/components/map/MapSearch.tsx",
            17,
            "searchValueNow",
            "    } else {",
            {"error", "logger", "targetSearch"},
            "targetSearch",
            6,
            4,
            "variable",
            {21},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real MapSearch regression: the missing-location logger line is not recovered with the expected trace/caller flow.",
            ),
        ),
        pytest.param(
            "advanced_fov/AdvancedFOVDialog.save_reset.tsx",
            "src/components/map/edit/AdvancedFOVDialog.tsx",
            10,
            "transformPoint",
            "    } catch (error) {",
            {"error", "logger"},
            "error",
            None,
            7,
            "variable",
            {41},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real AdvancedFOV regression: helper caller recovery does not find transformPoint usage from the component.",
            ),
        ),
        pytest.param(
            "advanced_fov/AdvancedFOVDialog.save_reset.tsx",
            "src/components/map/edit/AdvancedFOVDialog.tsx",
            19,
            "handleSave",
            "      if (!matrix) {",
            {"error", "logger"},
            "matrix",
            17,
            15,
            "variable",
            {41},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real AdvancedFOV regression: extract_function snaps to the if guard instead of the transformation-matrix logger line.",
            ),
        ),
        pytest.param(
            "advanced_fov/AdvancedFOVDialog.save_reset.tsx",
            "src/components/map/edit/AdvancedFOVDialog.tsx",
            30,
            "handleResetCalibration",
            "  const handleResetCalibration = useCallback(async () => {",
            {"error", "logger"},
            "onDeleteCalibration",
            4,
            28,
            "variable",
            {41},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real AdvancedFOV regression: extract_function snaps to the helper declaration instead of the no-delete-handler logger line.",
            ),
        ),
        pytest.param(
            "advanced_fov/AdvancedFOVDialog.save_reset.tsx",
            "src/components/map/edit/AdvancedFOVDialog.tsx",
            36,
            "handleResetCalibration",
            "    try {",
            {"error", "logger"},
            "error",
            None,
            28,
            "variable",
            {41},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real AdvancedFOV regression: extract_function expands the delete-calibration catch block instead of returning the logger.error line.",
            ),
        ),
    ],
)
def test_real_findings_follow_up_nx_maps_ui_should_keep_full_code_flow(
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
    assert extracted["meta"]["code_on_line"] == expected_line
    assert imports
    assert decorators == []
    assert identifiers["language"] == "typescript"
    assert reads_subset.issubset(set(identifiers["reads"]))
    if expected_trace_line is None:
        assert isinstance(trace, list)
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


