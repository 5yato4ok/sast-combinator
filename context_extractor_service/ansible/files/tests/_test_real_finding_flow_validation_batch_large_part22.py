# ruff: noqa: F403,F405
from _real_finding_flow_validation_batch_large_shared import *

@pytest.mark.parametrize(
    (
        "pipeline_id",
        "file_path",
        "line_number",
        "function_name",
        "expected_type",
        "expected_line",
        "reads_subset",
        "expected_writes_subset",
        "trace_symbol",
        "expected_trace_line",
        "expected_caller_lines",
        "expected_definition_line",
        "expected_definition_kind",
        "navigation_applicable",
    ),
    [
        (
            "5a36b942",
            "cloud/cms/static/js/menuChange.js",
            359,
            None,
            "production",
            "        window.location.href = window.location.pathname + '?' + queryParams.toString();",
            {"location", "pathname", "queryParams", "toString", "window"},
            {"href"},
            "queryParams",
            355,
            set(),
            None,
            None,
            False,
        ),
        (
            "5a36b942",
            "front_end/libs/services/nx-cloud-api/cloud-services/channel-partners/channel-partners-api.spec.ts",
            390,
            "getExpiringServiceDetailDialog",
            "test",
            "service.reports.organizations\n                .getExpiringServiceDetailDialog(orgId, serviceId, periodStartDate)\n                .subscribe",
            {"getExpiringServiceDetailDialog", "orgId", "organizations", "periodStartDate", "reports", "service", "serviceId", "subscribe"},
            set(),
            "orgId",
            385,
            {137, 389},
            None,
            None,
            False,
        ),
        pytest.param(
            "5a36b942",
            ".github/chatmodes/modules/git-operations.js",
            702,
            "runCommand",
            "production",
            "        const result = execSync(command, {",
            {"command", "cwd", "encoding", "execSync", "maxBuffer", "process", "timeout"},
            {"result"},
            "command",
            684,
            {55, 107, 116},
            684,
            "function",
            True,
            marks=pytest.mark.xfail(
                strict=True,
                reason="real finding flow: exact git-operations.js:702 line loses trace_identifier_backward for the runCommand parameter binding",
            ),
        ),
        pytest.param(
            "07734951",
            "src/lib/logging/logger.ts",
            117,
            "write",
            "production",
            "      console.error(prefix, ...args);",
            {"args", "console", "error", "prefix"},
            set(),
            "level",
            109,
            {119},
            109,
            "method",
            True,
            marks=pytest.mark.xfail(
                strict=True,
                reason="real finding flow: logger.ts:117 loses backward trace and definition resolution for write(), and find_callers is polluted by an internal sibling call",
            ),
        ),
        pytest.param(
            "07734951",
            "src/lib/logging/logger.ts",
            119,
            "write",
            "production",
            "      console.log(prefix, ...args);",
            {"args", "console", "log", "prefix"},
            set(),
            "prefix",
            113,
            {117},
            109,
            "method",
            True,
            marks=pytest.mark.xfail(
                strict=True,
                reason="real finding flow: logger.ts:119 resolves trace but still loses definition for write() and find_callers is polluted by the sibling console.error line",
            ),
        ),
        pytest.param(
            "07734951",
            "src/components/map/edit/AdvancedFOVDialog.tsx",
            167,
            None,
            "production",
            "          y: result.lat",
            {"lat", "result"},
            set(),
            "result",
            166,
            set(),
            None,
            None,
            False,
            marks=pytest.mark.xfail(
                strict=True,
                reason="real finding flow: AdvancedFOVDialog.tsx:167 expands the return object block instead of preserving the exact property line and loses backward trace for result",
            ),
        ),
        (
            "9ce90895",
            "vms/server/plugins/analytics/nx_ai_manager_plugin/nxai_utilities/src/nxai_shm_utils.cpp",
            47,
            None,
            "production",
            "    char* shm_key_string = (char*) malloc(strlen(shm.key));",
            {"key", "malloc", "shm", "strlen"},
            {"shm_key_string"},
            None,
            None,
            set(),
            None,
            None,
            False,
        ),
        pytest.param(
            "9ce90895",
            "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_administration/widgets/security_settings_widget.cpp",
            411,
            "SecuritySettingsWidget",
            "production",
            "    auto dialog = new PixelationIntensityDialog(",
            {"intensity", "m_pixelationSettings", "mainWindowWidget"},
            {"dialog"},
            None,
            None,
            {306},
            281,
            "class",
            True,
            marks=pytest.mark.xfail(
                strict=True,
                reason="real finding flow: SecuritySettingsWidget constructor line loses definition resolution and find_callers is polluted by destructor/definition-site hits",
            ),
        ),
        pytest.param(
            "9ce90895",
            "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_health/cloud_storage_watcher.cpp",
            15,
            "CloudStorageWatcher",
            "production",
            "    auto storageChangesListener = new core::SessionResourcesSignalListener<QnStorageResource>(",
            {"QnStorageResource", "SessionResourcesSignalListener", "systemContext", "this"},
            {"storageChangesListener"},
            None,
            None,
            {85},
            12,
            "class",
            True,
            marks=pytest.mark.xfail(
                strict=True,
                reason="real finding flow: CloudStorageWatcher constructor line loses definition resolution and find_callers is polluted by destructor/definition-site hits",
            ),
        ),
        pytest.param(
            "9ce90895",
            "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/logic/connect_actions_handler.cpp",
            336,
            "ConnectActionsHandler",
            "production",
            "",
            {"connectTimeout", "crashReporter", "resourceModeAction", "sessionTimeoutWatcher"},
            set(),
            None,
            None,
            {567},
            147,
            "class",
            True,
            marks=pytest.mark.xfail(
                strict=True,
                reason="real finding flow: ConnectActionsHandler constructor finding line collapses to empty code_on_line and find_callers is polluted by destructor/definition-site hits",
            ),
        ),
        (
            "9ce90895",
            "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/logic/connect_actions_handler.cpp",
            533,
            None,
            "production",
            "",
            {"instance", "workbenchContext"},
            {"errorCode"},
            "errorCode",
            310,
            set(),
            None,
            None,
            False,
        ),
        pytest.param(
            "9ce90895",
            "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/ui/server_certificate_warning.cpp",
            136,
            "ServerCertificateWarning",
            "production",
            "                        auto viewer = new ServerCertificateViewer(",
            {"ServerCertificateViewer", "certificateInfo", "presented", "this"},
            {"viewer"},
            None,
            None,
            set(),
            24,
            "function",
            True,
            marks=pytest.mark.xfail(
                strict=True,
                reason="real finding flow: ServerCertificateWarning line resolves identifiers correctly but still loses constructor definition resolution",
            ),
        ),
        pytest.param(
            "9ce90895",
            "open/vms/client/nx_vms_client_desktop/src/ui/widgets/properties/server_settings_widget.cpp",
            607,
            "ServerSettingsWidget",
            "production",
            "    auto viewer = new ServerCertificateViewer(m_server, certificate, mode, systemContext(), this);",
            {"ServerCertificateViewer", "certificate", "m_server", "mode", "systemContext", "this"},
            {"viewer"},
            None,
            None,
            set(),
            59,
            "function",
            True,
            marks=pytest.mark.xfail(
                strict=True,
                reason="real finding flow: ServerSettingsWidget viewer-construction line loses enclosing function/class definition resolution",
            ),
        ),
        pytest.param(
            "9ce90895",
            "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/ui/server_certificate_viewer.cpp",
            153,
            "ServerCertificateViewer",
            "production",
            "    auto aligner = new nx::vms::client::desktop::Aligner(this);",
            {"Aligner", "this"},
            {"aligner"},
            None,
            None,
            {368},
            54,
            "function",
            True,
            marks=pytest.mark.xfail(
                strict=True,
                reason="real finding flow: ServerCertificateViewer line loses constructor definition resolution and find_callers includes constructor/destructor definition-site noise",
            ),
        ),
        pytest.param(
            "9ce90895",
            "open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/system_logon/ui/welcome_screen.cpp",
            331,
            "WelcomeScreen",
            "production",
            "    auto dialog = new QnMessageBox(",
            {"Cancel", "NoButton", "QnMessageBox", "Question", "arg", "cloudName", "parentWidget", "tr"},
            {"dialog"},
            None,
            None,
            {136},
            63,
            "class",
            True,
            marks=pytest.mark.xfail(
                strict=True,
                reason="real finding flow: WelcomeScreen dialog-construction line loses definition resolution and find_callers is polluted by destructor/definition-site hits",
            ),
        ),
    ],
)
def test_real_findings_exact_source_batch_should_keep_full_flow(
    monkeypatch,
    pipeline_id,
    file_path,
    line_number,
    function_name,
    expected_type,
    expected_line,
    reads_subset,
    expected_writes_subset,
    trace_symbol,
    expected_trace_line,
    expected_caller_lines,
    expected_definition_line,
    expected_definition_kind,
    navigation_applicable,
    tmp_path,
):
    source = _real_source_text(pipeline_id, file_path)
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, Path(file_path).name))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)
    local_line_number = _map_fixture_line(pipeline_id, file_path, line_number)
    local_expected_trace_line = _map_fixture_line(pipeline_id, file_path, expected_trace_line)
    local_expected_caller_lines = {_map_fixture_line(pipeline_id, file_path, line) for line in expected_caller_lines}
    local_expected_definition_line = _map_fixture_line(pipeline_id, file_path, expected_definition_line)

    classification = mcp_server.classify_file(pipeline_id, file_path)
    extracted = mcp_server.extract_function(pipeline_id, file_path, local_line_number)
    imports = mcp_server.find_imports(pipeline_id, file_path)
    decorators = mcp_server.find_decorators(pipeline_id, file_path, local_line_number)
    identifiers = mcp_server.find_identifiers(pipeline_id, file_path, local_line_number)
    trace = mcp_server.trace_identifier_backward(pipeline_id, file_path, local_line_number, trace_symbol)

    assert classification["type"] == expected_type
    assert isinstance(imports, list)
    assert decorators == []
    assert extracted["meta"]["code_on_line"] == expected_line
    assert reads_subset.issubset(set(identifiers["reads"]))
    assert expected_writes_subset.issubset(set(identifiers["writes"]))
    if local_expected_trace_line is None:
        assert trace == []
    else:
        assert trace
        assert trace[0]["line"] == local_expected_trace_line

    if not navigation_applicable:
        return

    callers = mcp_server.find_callers(pipeline_id, file_path, function_name)
    definition = mcp_server.find_definition(pipeline_id, function_name)
    route = mcp_server.find_route_to_function(pipeline_id, function_name)

    assert local_expected_caller_lines.issubset({item["line"] for item in callers if item["file"] == file_path})
    assert any(
        item["file"] == file_path and item["line"] == local_expected_definition_line and item["kind"] == expected_definition_kind
        for item in definition
    )
    assert route == []
