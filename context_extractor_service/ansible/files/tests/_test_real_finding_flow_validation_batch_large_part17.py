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
        "expected_writes_subset",
        "trace_symbol",
        "expected_trace_line",
        "expected_definition_line",
        "expected_definition_kind",
    ),
    [
        (
            "nx_connect/entity_information/EditServiceDialog.tsx",
            "app/(dashboard)/components/EntityInformation/EditServiceDialog/EditServiceDialog.tsx",
            11,
            "EditServiceDialog",
            "  const SERVICE_SUBTYPE_DEMO = 'demo';",
            set(),
            {"SERVICE_SUBTYPE_DEMO"},
            "SERVICE_SUBTYPE_DEMO",
            11,
            3,
            "function",
        ),
        (
            "nx_connect/entity_information/EditServiceDialog.tsx",
            "app/(dashboard)/components/EntityInformation/EditServiceDialog/EditServiceDialog.tsx",
            18,
            "EditServiceDialog",
            "      await patchService(servicePrice);",
            {"patchService", "servicePrice"},
            set(),
            "servicePrice",
            17,
            3,
            "function",
        ),
        (
            "nx_connect/entity_information/CompanyInformationForm.tsx",
            "app/(dashboard)/channel-partners/components/ChannelPartnerForm/CompanyInformationForm/CompanyInformationForm.tsx",
            7,
            "CompanyInformationForm",
            "  const getEditTypeFromCacheKey = (_key: string) => 'edit';",
            {"_key"},
            {"getEditTypeFromCacheKey"},
            "_key",
            None,
            3,
            "function",
        ),
        (
            "nx_connect/entity_information/CompanyInformationForm.tsx",
            "app/(dashboard)/channel-partners/components/ChannelPartnerForm/CompanyInformationForm/CompanyInformationForm.tsx",
            20,
            "CompanyInformationForm",
            "    changedData.name = safeTrim(formData.name);",
            {"changedData", "formData", "name", "safeTrim"},
            {"name"},
            "formData",
            13,
            3,
            "function",
        ),
        (
            "nx_connect/entity_information/ContactInformationForm.tsx",
            "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ContactInformationForm/ContactInformationForm.tsx",
            6,
            "ContactInformationForm",
            "  const getValues = () => ({ contacts: [{ email: 'a@example.test' }] });",
            set(),
            {"getValues"},
            "getValues",
            6,
            3,
            "function",
        ),
        pytest.param(
            "nx_connect/entity_information/ContactInformationForm.tsx",
            "app/(dashboard)/channel-partners/components/ChannelPartnerForm/ContactInformationForm/ContactInformationForm.tsx",
            18,
            "ContactInformationForm",
            "      contacts: pruneEmptyStrings(formData.contacts),",
            {"contacts", "formData", "pruneEmptyStrings"},
            {"changedData"},
            "formData",
            15,
            3,
            "function",
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    "Real ContactInformationForm regression: extract_function returns the whole changedData object "
                    "instead of the exact contacts property line."
                ),
            ),
        ),
        (
            "nx_connect/company_contact/ChannelPartnerPage.tsx",
            "app/(dashboard)/channel-partners/[id]/page.tsx",
            2,
            "ChannelPartnerDetails",
            "	const resizeWindow = () => {};",
            set(),
            {"resizeWindow"},
            "resizeWindow",
            2,
            1,
            "function",
        ),
        (
            "nx_connect/company_contact/ChannelPartnerPage.tsx",
            "app/(dashboard)/channel-partners/[id]/page.tsx",
            4,
            "ChannelPartnerDetails",
            "		resizeWindow();",
            {"resizeWindow"},
            set(),
            "resizeWindow",
            2,
            1,
            "function",
        ),
    ],
)
def test_real_findings_nx_connect_forms_and_page_batch_should_keep_full_flow(
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
            set(),
            "typescript",
        ),
        (
            "69ec5b01",
            "nx_connect/entity_information/TiersForm.tsx",
            "app/(dashboard)/channel-partners/components/ChannelPartnerForm/TiersForm/TiersForm.tsx",
            6,
            "TiersForm",
            "  const tierAdditionalInfo: Record<number, unknown> = {};",
            set(),
            {"tierAdditionalInfo"},
            "tierAdditionalInfo",
            6,
            3,
            "function",
            set(),
            "typescript",
        ),
        (
            "69ec5b01",
            "nx_connect/entity_information/TiersForm.tsx",
            "app/(dashboard)/channel-partners/components/ChannelPartnerForm/TiersForm/TiersForm.tsx",
            12,
            "TiersForm",
            "  const addTiersToSubChannelPartner = async (_root: string, _id: string, _items: number[]) => {};",
            {"_id", "_items", "_root"},
            {"addTiersToSubChannelPartner"},
            "_root",
            None,
            3,
            "function",
            set(),
            "typescript",
        ),
        (
            "5a36b942",
            "cloud_portal/main_modules/get_zip_from_cloud.py",
            ".github/chatmodes/modules/get_zip_from_cloud.py",
            6,
            "main",
            '    main(["archive.zip"])',
            {"main"},
            set(),
            "main",
            None,
            1,
            "function",
            {6},
            "python",
        ),
    ],
)
def test_real_findings_settings_tiers_and_python_entrypoint_batch_should_keep_full_flow(
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


