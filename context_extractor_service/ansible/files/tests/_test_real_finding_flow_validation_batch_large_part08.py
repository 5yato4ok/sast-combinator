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
            "nx_maps_ui/oauth_page.tsx",
            "src/app/auth/oauth/page.tsx",
            38,
            "extractSystemIdFromReturnUrl",
            "      logger.warn('[OAuth]: Failed to extract systemId from returnUrl:', error);",
            {"error", "logger", "warn"},
            "error",
            None,
            23,
            "variable",
            {105, 128},
        ),
        pytest.param(
            "nx_maps_ui/oauth_page.tsx",
            "src/app/auth/oauth/page.tsx",
            63,
            "getSystems",
            "        logger.warn('[OAuth]: Unexpected systems response structure:', data);",
            {"data", "logger", "warn"},
            "data",
            53,
            43,
            "variable",
            {101, 124},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real helper-flow regression: find_callers misses local getSystems invocations in OAuthPage fixture.",
            ),
        ),
        pytest.param(
            "nx_maps_ui/oauth_page.tsx",
            "src/app/auth/oauth/page.tsx",
            78,
            "getTokenForSystem",
            "        logger.warn('[OAuth]: Primary token endpoint failed, trying CDB OAuth2 fallback:', error.response?.data);",
            {"data", "error", "logger", "response", "warn"},
            "error",
            None,
            73,
            "variable",
            {86},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real helper-flow regression: find_callers misses local getTokenForSystem invocation from handleSystemSelection.",
            ),
        ),
        (
            "nx_maps_ui/auth_guard.tsx",
            "src/components/auth/auth-guard.tsx",
            19,
            "handleOAuthLogin",
            "        logger.error('[Auth]: Failed to get system info:', systemInfoResult.error);",
            {"error", "logger", "systemInfoResult"},
            "systemInfoResult",
            16,
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
            24,
            "handleOAuthLogin",
            "      logger.error('[Auth]: OAuth login failed', error);",
            {"error", "logger"},
            "error",
            None,
            14,
            "variable",
            {50},
        ),
        (
            "nx_maps_ui/auth_guard.tsx",
            "src/components/auth/auth-guard.tsx",
            34,
            "checkPermissions",
            "      logger.error('[Auth]: Failed to get system info:', systemInfoResult.error);",
            {"error", "logger", "systemInfoResult"},
            "systemInfoResult",
            32,
            31,
            "variable",
            {42},
        ),
        pytest.param(
            "nx_maps_ui/layout.tsx",
            "src/app/layout.tsx",
            9,
            "RootLayout",
            "    <html lang=\"en\">",
            {"React", "config", "createElement"},
            "config",
            None,
            6,
            "function",
            set(),
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real JSX/XSS regression: extract_function loses the React.createElement line and snaps to the enclosing <html> node.",
            ),
        ),
        pytest.param(
            "nx_maps_ui/MapSearch.tsx",
            "src/components/map/MapSearch.tsx",
            16,
            "handleSelectionChange",
                    "                    logger.error('Invalid coordinates for geocoding result:', selectedOption);",
            {"error", "logger", "selectedOption"},
            "selectedOption",
            4,
            4,
            "variable",
            {38},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real data-flow regression: trace_identifier_backward does not resolve selectedOption from handleSelectionChange parameters.",
            ),
        ),
        (
            "nx_maps_ui/MapSearch.tsx",
            "src/components/map/MapSearch.tsx",
            35,
            "searchValueNow",
                "                logger.error('Error parsing nxmaps data:', e);",
            {"e", "error", "logger"},
            "targetSearch",
            24,
            23,
            "variable",
            {12},
        ),
    ],
)
def test_real_findings_from_live_run_tree_should_keep_full_code_flow(
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
            "nx_maps_ui/config.ts",
            "src/config.ts",
            9,
            "loadBrandConfig",
            "  } catch (error) {",
            {"console", "customization", "error", "warn"},
            "customization",
            4,
            3,
            "function",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real config-flow regression: extract_function snaps to the catch line instead of the console.warn finding line.",
            ),
        ),
        pytest.param(
            "nx_maps_ui/geocode-search.ts",
            "src/components/map/search/geocode-search.ts",
            16,
            "geocodeSearch",
            "    } catch (error) {",
            {"error", "logger"},
            "error",
            None,
            3,
            "variable",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real geocode-flow regression: extract_function returns the catch header instead of the logger.error finding line.",
            ),
        ),
        pytest.param(
            "nx_maps_ui/useBackgroundWebRTC.ts",
            "src/hooks/map/useBackgroundWebRTC.ts",
            13,
            "disconnectAll",
            "          await client.disconnect();",
            {"err", "error", "logger"},
            "client",
            8,
            6,
            "variable",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real WebRTC cleanup regression: extract_function shifts to await client.disconnect() instead of the logger.error line.",
            ),
        ),
        pytest.param(
            "nx_maps_ui/useCalibrationActions.ts",
            "src/hooks/map/editing/useCalibrationActions.ts",
            7,
            "handleSaveCalibration",
            "    } catch (error) {",
            {"error", "logger"},
            "error",
            None,
            4,
            "variable",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real calibration regression: extract_function returns the catch line instead of the save logger.error line.",
            ),
        ),
        pytest.param(
            "nx_maps_ui/useCalibrationActions.ts",
            "src/hooks/map/editing/useCalibrationActions.ts",
            15,
            "handleDeleteCalibration",
            "      logger.debug('Calibration deleted successfully');",
            {"error", "logger"},
            "error",
            None,
            12,
            "variable",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real calibration regression: extract_function lands on the success logger instead of the delete error logger line.",
            ),
        ),
        pytest.param(
            "nx_maps_ui/useCalibrationActions.ts",
            "src/hooks/map/editing/useCalibrationActions.ts",
            25,
            "handleAdvancedFov",
            "      const thumbnailUrl = URL.createObjectURL(response.data);",
            {"error", "logger"},
            "response",
            22,
            20,
            "variable",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real Advanced FOV regression: extract_function returns the thumbnail creation line instead of the error logger line.",
            ),
        ),
    ],
)
def test_real_findings_misc_nx_maps_ui_should_keep_full_code_flow(
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
    assert identifiers["language"] in {"typescript", "javascript"}
    assert reads_subset.issubset(set(identifiers["reads"]))
    if expected_trace_line is None:
        assert isinstance(trace, list)
    else:
        assert trace
        assert trace[0]["line"] == expected_trace_line
    assert callers == []
    assert any(
        item["file"] == file_path and item["line"] == expected_definition_line and item["kind"] == expected_definition_kind
        for item in definition
    )
    assert route == []


