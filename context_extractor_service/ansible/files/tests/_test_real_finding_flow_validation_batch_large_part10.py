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
        pytest.param(
            "nx_connect/entity_information/EditServiceDialog.tsx",
            "app/(dashboard)/components/EntityInformation/EditServiceDialog/EditServiceDialog.tsx",
            24,
            "EditServiceDialog",
            "    },",
            {"console", "error"},
            "error",
            None,
            3,
            "function",
            set(),
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real EditServiceDialog regression: extract_function snaps away from the update-service console.error line.",
            ),
        ),
        pytest.param(
            "nx_connect/entity_information/EditServiceDialog.tsx",
            "app/(dashboard)/components/EntityInformation/EditServiceDialog/EditServiceDialog.tsx",
            35,
            "EditServiceDialog",
            "      await queryClient.refetchQueries('subChannelPartnerServices');",
            {"console", "error"},
            "error",
            None,
            3,
            "function",
            set(),
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real EditServiceDialog regression: extract_function snaps away from the remove-service console.error line.",
            ),
        ),
        pytest.param(
            "nx_connect/entity_information/SettingsForm.errors.tsx",
            "app/(dashboard)/components/EntityInformation/SettingsForm/SettingsForm.tsx",
            16,
            "saveSettings",
            "      await updateChannelPartnerAccessLevel('id', 2);",
            {"console", "error"},
            "error",
            None,
            13,
            "variable",
            {39},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real SettingsForm regression: extract_function returns the awaited CPAL update call instead of the console.error line.",
            ),
        ),
        pytest.param(
            "nx_connect/entity_information/SettingsForm.errors.tsx",
            "app/(dashboard)/components/EntityInformation/SettingsForm/SettingsForm.tsx",
            23,
            "saveSettings",
            "      await updateUsageBasedBilling('id', true);",
            {"console", "error"},
            "error",
            None,
            13,
            "variable",
            {39},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real SettingsForm regression: extract_function misses the usage-based-billing console.error line.",
            ),
        ),
        pytest.param(
            "nx_connect/entity_information/SettingsForm.errors.tsx",
            "app/(dashboard)/components/EntityInformation/SettingsForm/SettingsForm.tsx",
            33,
            "saveSettings",
            "      await refetchOrganizationCustomId();",
            {"console", "error"},
            "error",
            None,
            13,
            "variable",
            {39},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real SettingsForm regression: extract_function misses the custom-id console.error line.",
            ),
        ),
        pytest.param(
            "nx_connect/entity_information/TiersForm.tsx",
            "app/(dashboard)/components/EntityInformation/TiersForm/TiersForm.tsx",
            32,
            "checkTiers",
            "          }",
            {"console", "error", "tierId"},
            "tierId",
            18,
            17,
            "variable",
            {60},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real TiersForm regression: extract_function collapses the tier-checking catch to a brace instead of the console.error line.",
            ),
        ),
        pytest.param(
            "nx_connect/entity_information/TiersForm.tsx",
            "app/(dashboard)/components/EntityInformation/TiersForm/TiersForm.tsx",
            47,
            "handleSaveAndProceedClick",
            "      await addTiersToSubChannelPartner(rootChannelPartner.id, individualCpOrOrg.id, newSelections);",
            {"console", "e", "error"},
            "e",
            None,
            39,
            "variable",
            {64},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real TiersForm regression: extract_function returns the awaited addTiers call instead of the addTiers console.error line.",
            ),
        ),
        pytest.param(
            "nx_connect/entity_information/TiersForm.tsx",
            "app/(dashboard)/components/EntityInformation/TiersForm/TiersForm.tsx",
            56,
            "handleSaveAndProceedClick",
            "      );",
            {"console", "e", "error"},
            "e",
            None,
            39,
            "variable",
            {64},
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real TiersForm regression: extract_function expands the removeTier callback body instead of the console.error line.",
            ),
        ),
    ],
)
def test_real_findings_entity_information_batch_should_keep_full_flow(
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
    assert extracted["meta"]["code_on_line"] == expected_line
    assert isinstance(imports, list)
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
        "pipeline_id",
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
        "expected_classification",
    ),
    [
        pytest.param(
            "69ec5b01",
            "nx_connect/entity_information/CompanyInformationForm.tsx",
            "app/(dashboard)/components/EntityInformation/CompanyInformationForm/CompanyInformationForm.tsx",
            41,
            "CompanyInformationForm",
            "    refetchEntity = true;",
            {"console", "error"},
            "error",
            None,
            3,
            "function",
            "production",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real CompanyInformationForm regression: extract_function returns refetchEntity assignment instead of the console.error line.",
            ),
        ),
        pytest.param(
            "69ec5b01",
            "nx_connect/entity_information/ContactInformationForm.tsx",
            "app/(dashboard)/components/EntityInformation/ContactInformationForm/ContactInformationForm.tsx",
            25,
            "ContactInformationForm",
            "    refetchEntity = true;",
            {"console", "error"},
            "error",
            None,
            3,
            "function",
            "production",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real ContactInformationForm regression: extract_function returns refetchEntity assignment instead of the console.error line.",
            ),
        ),
        pytest.param(
            "5a36b942",
            "cloud_portal/git_operations_parent_branch.js",
            ".github/chatmodes/modules/git-operations.js",
            14,
            "getParentBranch",
            "      if (process.env.DEBUG) {",
            {"console", "env", "error", "process"},
            "error",
            None,
            6,
            "function",
            "production",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real git-operations regression: extract_function snaps to the DEBUG guard instead of the parent-branch console.error line.",
            ),
        ),
        pytest.param(
            "9ce90895",
            "nx/run_after_fetch.py",
            "build_utils/python/run_after_fetch.py",
            12,
            "run_after_fetch",
            "    script = __import__(args.checker_run_script)",
            {"__import__", "args"},
            "args",
            5,
            5,
            "function",
            "production",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real run_after_fetch regression: extract_function loses the __import__ assignment line and returns empty code_on_line.",
            ),
        ),
    ],
)
def test_real_findings_company_contact_git_python_batch_should_keep_full_flow(
    monkeypatch,
    pipeline_id,
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
    expected_classification,
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

    assert classification["type"] == expected_classification
    assert extracted["meta"]["code_on_line"] == expected_line
    assert isinstance(imports, list)
    assert decorators == []
    assert identifiers["language"] in {"typescript", "javascript", "python"}
    assert reads_subset.issubset(set(identifiers["reads"]))
    if expected_trace_line is None:
        assert isinstance(trace, list)
    else:
        assert trace
        assert trace[0]["line"] == expected_trace_line
    assert isinstance(callers, list)
    assert any(
        item["file"] == file_path and item["line"] == expected_definition_line and item["kind"] == expected_definition_kind
        for item in definition
    )
    assert route == []


