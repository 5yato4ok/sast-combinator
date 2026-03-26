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
        "expected_language",
    ),
    [
        (
            "69ec5b01",
            "nx_connect/logo/ExternalLogo.tsx",
            "app/(dashboard)/components/Logo/ExternalLogo.tsx",
            5,
            "Logo",
            "const Logo = ({ configData }: LogoProps) => {",
            {"configData", "systemTheme", "theme", "useTheme"},
            {"Logo"},
            "Logo",
            None,
            5,
            "variable",
            set(),
            "typescript",
        ),
        (
            "69ec5b01",
            "nx_connect/logo/ExternalLogo.tsx",
            "app/(dashboard)/components/Logo/ExternalLogo.tsx",
            6,
            "Logo",
            "	const { theme, systemTheme } = useTheme();",
            {"useTheme"},
            set(),
            "useTheme",
            None,
            5,
            "variable",
            set(),
            "typescript",
        ),
        (
            "69ec5b01",
            "nx_connect/logo/ExternalLogo.tsx",
            "app/(dashboard)/components/Logo/ExternalLogo.tsx",
            7,
            "Logo",
            "	return configData || theme || systemTheme;",
            {"configData", "systemTheme", "theme"},
            set(),
            "configData",
            None,
            5,
            "variable",
            set(),
            "typescript",
        ),
        (
            "69ec5b01",
            "nx_connect/company_contact/SubscriptionKeysTable.tsx",
            "app/(dashboard)/channel-partners/[id]/components/SubscriptionKeysTable.tsx",
            2,
            "SubscriptionKeysTable",
            "	const resizeWindow = () => {};",
            set(),
            {"resizeWindow"},
            "resizeWindow",
            2,
            1,
            "function",
            set(),
            "typescript",
        ),
        (
            "69ec5b01",
            "nx_connect/company_contact/SubscriptionKeysTable.tsx",
            "app/(dashboard)/channel-partners/[id]/components/SubscriptionKeysTable.tsx",
            4,
            "SubscriptionKeysTable",
            "		resizeWindow();",
            {"resizeWindow"},
            set(),
            "resizeWindow",
            2,
            1,
            "function",
            set(),
            "typescript",
        ),
        (
            "5a36b942",
            "cloud_portal/main_modules/check_dependencies.py",
            ".github/chatmodes/modules/check_dependencies.py",
            5,
            "main",
            'main("pyproject.toml")',
            {"main"},
            set(),
            "main",
            None,
            1,
            "function",
            {5},
            "python",
        ),
        (
            "5a36b942",
            "cloud_portal/main_modules/extract_brand_core_values.py",
            ".github/chatmodes/modules/extract_brand_core_values.py",
            5,
            "main",
            'colors = main("palette.scss")',
            {"main"},
            {"colors"},
            "main",
            None,
            1,
            "function",
            {5},
            "python",
        ),
    ],
)
def test_real_findings_logo_table_and_python_entrypoints_batch_should_keep_full_flow(
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
    expected_language,
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
    assert isinstance(imports, list)
    assert decorators == []
    assert extracted["meta"]["code_on_line"] == expected_line
    assert identifiers["language"] == expected_language
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


@pytest.mark.parametrize(
    (
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
    ),
    [
        (
            "nx_connect/alert/Alert.tsx",
            "app/components/Alert/Alert.tsx",
            8,
            "Alert",
            "					<InfoIcon width={40} height={40} />",
            {"InfoIcon"},
            set(),
            "InfoIcon",
            None,
            3,
            "function",
        ),
        (
            "nx_connect/settings/ProfileSettings.tsx",
            "app/(dashboard)/settings/ProfileSettings.tsx",
            5,
            "ProfileSettings",
            "export default function ProfileSettings() {",
            {"console", "data", "log", "onSubmit", "register", "useForm"},
            {"ProfileSettings"},
            "ProfileSettings",
            None,
            5,
            "function",
        ),
        (
            "nx_connect/entity_information/SettingsForm.errors.tsx",
            "app/(dashboard)/channel-partners/components/ChannelPartnerForm/SettingsForm/SettingsForm.tsx",
            8,
            "SettingsForm",
            "  const refetchChannelPartnerCustomId = async () => {};",
            set(),
            {"refetchChannelPartnerCustomId"},
            "refetchChannelPartnerCustomId",
            8,
            3,
            "function",
        ),
        (
            "nx_connect/forms/AddSubscriptionForm.tsx",
            "app/(dashboard)/subscriptions/AddSubscriptionForm.tsx",
            10,
            "AddSubscriptionForm",
            "	const watchSystem = watch('system');",
            {"watch"},
            {"watchSystem"},
            "watch",
            None,
            8,
            "function",
        ),
        (
            "nx_connect/forms/AddServiceForm.tsx",
            "app/(dashboard)/services/AddServiceForm.tsx",
            5,
            "AddServiceForm",
            "export default function AddServiceForm() {",
            {"console", "data", "log", "onSubmit", "register", "useForm"},
            {"AddServiceForm"},
            "AddServiceForm",
            None,
            5,
            "function",
        ),
    ],
)
def test_real_findings_alert_settings_and_forms_batch_should_keep_full_flow(
    monkeypatch,
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
    tmp_path,
):
    source = _fixture_text(fixture_path)
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, Path(file_path).name))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, line_number)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, line_number)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, line_number)
    trace = mcp_server.trace_identifier_backward("69ec5b01", file_path, line_number, trace_symbol)
    callers = mcp_server.find_callers("69ec5b01", file_path, function_name)
    definition = mcp_server.find_definition("69ec5b01", function_name)
    route = mcp_server.find_route_to_function("69ec5b01", function_name)

    assert classification["type"] == "production"
    assert isinstance(imports, list)
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
    assert callers == []
    assert any(
        item["file"] == file_path and item["line"] == expected_definition_line and item["kind"] == expected_definition_kind
        for item in definition
    )
    assert route == []


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Real ReportDownloader regression: find_callers(getNextFibonacci) still returns the definition site "
        "in addition to real invocation sites."
    ),
)
def test_real_finding_report_downloader_should_keep_callers_without_definition_pollution(monkeypatch, tmp_path):
    source = _fixture_text("nx_connect/usage/ReportDownloader.ts")
    file_path = "app/(dashboard)/usage/ReportDownloader.ts"
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "ReportDownloader.ts"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, 9)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, 9)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, 9)
    trace = mcp_server.trace_identifier_backward("69ec5b01", file_path, 9, "getNextFibonacci")
    callers = mcp_server.find_callers("69ec5b01", file_path, "getNextFibonacci")
    definition = mcp_server.find_definition("69ec5b01", "getNextFibonacci")
    route = mcp_server.find_route_to_function("69ec5b01", "getNextFibonacci")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "\t\treturn 1;"
    assert imports == ["import axios from '@/app/axiosInstance';", "import { isAxiosError } from 'axios';"]
    assert decorators == []
    assert identifiers == {"reads": [], "writes": [], "language": "typescript"}
    assert trace == []
    assert callers == [
        {"file": file_path, "line": 22, "caller_function": "checkFileAvailability", "snippet": callers[0]["snippet"]},
        {"file": file_path, "line": 32, "caller_function": "checkFileAvailability", "snippet": callers[1]["snippet"]},
    ]
    assert any(item["file"] == file_path and item["line"] == 8 and item["kind"] == "function" for item in definition)
    assert route == []


