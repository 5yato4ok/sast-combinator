# ruff: noqa: F403,F405
from _real_finding_flow_validation_batch_large_shared import *

@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real ReportDownloader findings. "
        "For recursive method checkFileAvailability, find_callers is still unstable and "
        "pollutes caller discovery instead of returning only the expected self-call sites."
    ),
)
@pytest.mark.parametrize(
    ("line_number", "code_on_line", "reads", "writes", "trace_symbol", "trace_expected"),
    [
        (
            23,
            "\t\t\t\t\tconsole.log('File not yet available, retrying in', interval, 'seconds');",
            ["console", "interval", "log"],
            [],
            "interval",
            [{"line": 22, "code": "const interval = this.getNextFibonacci();", "writes": ["interval"], "reads": ["getNextFibonacci", "this"]}],
        ),
        (
            26,
            "\t\t\t\t\tconsole.error('Unexpected status:', response.data.status);",
            ["console", "data", "error", "response", "status"],
            [],
            "response",
            [{"line": 17, "code": "const response = await axios.get(this.checkUrl.replace('{reportId}', reportId));", "writes": ["response"], "reads": ["axios", "checkUrl", "get", "replace", "reportId", "this"]}],
        ),
        (
            33,
            "\t\t\t\tconsole.log('File not found, retrying in', interval, 'seconds');",
            ["console", "interval", "log"],
            [],
            "interval",
            [{"line": 32, "code": "const interval = this.getNextFibonacci();", "writes": ["interval"], "reads": ["getNextFibonacci", "this"]}],
        ),
    ],
)
def test_real_finding_report_downloader_should_keep_real_flow(
    monkeypatch,
    tmp_path,
    line_number,
    code_on_line,
    reads,
    writes,
    trace_symbol,
    trace_expected,
):
    source = _fixture_text("nx_connect/usage/ReportDownloader.ts")
    _write_source_tree(tmp_path, "app/(dashboard)/usage-statements/ReportDownloader.ts", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "ReportDownloader.ts"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "app/(dashboard)/usage-statements/ReportDownloader.ts"
    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, line_number)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, line_number)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, line_number)
    trace = mcp_server.trace_identifier_backward("69ec5b01", file_path, line_number, trace_symbol)
    callers = mcp_server.find_callers("69ec5b01", file_path, "checkFileAvailability")
    definition = mcp_server.find_definition("69ec5b01", "checkFileAvailability")
    route = mcp_server.find_route_to_function("69ec5b01", "checkFileAvailability")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == code_on_line
    assert "import axios from '@/app/axiosInstance';" in imports
    assert "import { isAxiosError } from 'axios';" in imports
    assert decorators == []
    assert identifiers == {"reads": reads, "writes": writes, "language": "typescript"}
    assert trace == trace_expected
    assert callers == []
    assert definition == [{"file": file_path, "line": 14, "kind": "method", "snippet": definition[0]["snippet"]}]
    assert route == []


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real nx-connect-ui finding on StatusForm.tsx:60. "
        "For a multiline hook call, extract_function still returns the whole block in code_on_line "
        "instead of the exact finding line."
    ),
)
def test_real_finding_status_form_multiline_hook_should_keep_exact_line(monkeypatch, tmp_path):
    source = _fixture_text("nx_connect/status_form/StatusForm.tsx")
    _write_source_tree(
        tmp_path,
        "app/(dashboard)/components/EntityInformation/StatusForm/StatusForm.tsx",
        source,
    )
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "StatusForm.tsx"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "app/(dashboard)/components/EntityInformation/StatusForm/StatusForm.tsx"
    classification = mcp_server.classify_file("69ec5b01", file_path)
    extracted = mcp_server.extract_function("69ec5b01", file_path, 8)
    imports = mcp_server.find_imports("69ec5b01", file_path)
    decorators = mcp_server.find_decorators("69ec5b01", file_path, 8)
    identifiers = mcp_server.find_identifiers("69ec5b01", file_path, 8)
    trace = mcp_server.trace_identifier_backward("69ec5b01", file_path, 8, "hasUnsavedChanges")
    callers = mcp_server.find_callers("69ec5b01", file_path, "StatusForm")
    definition = mcp_server.find_definition("69ec5b01", "StatusForm")
    route = mcp_server.find_route_to_function("69ec5b01", "StatusForm")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "\tconst { isSaving } = useEditEntityFormRef("
    assert "import { useEditEntityFormRef } from '@/app/(dashboard)/components/EntityInformation/hooks/useEditEntityFormRef';" in imports
    assert decorators == []
    assert identifiers == {
        "reads": ["handleSaveButtonClick", "hasUnsavedChanges", "individualCpOrOrg", "ref", "saveAndExit", "selectedEntityState", "useEditEntityFormRef"],
        "writes": ["isSaving"],
        "language": "typescript",
    }
    assert trace == [{"line": 5, "code": "\tconst hasUnsavedChanges = () => true;", "writes": ["hasUnsavedChanges"], "reads": []}]
    assert callers == []
    assert definition == [{"file": file_path, "line": 3, "kind": "variable", "snippet": definition[0]["snippet"]}]
    assert route == []


def test_real_finding_generate_customization_write_should_keep_real_flow(monkeypatch, tmp_path):
    source = _fixture_text("nx_maps/generate_customization_write.js")
    _write_source_tree(tmp_path, "scripts/generate-customization.js", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "generate-customization.js"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "scripts/generate-customization.js"
    classification = mcp_server.classify_file("07734951", file_path)
    extracted = mcp_server.extract_function("07734951", file_path, 6)
    imports = mcp_server.find_imports("07734951", file_path)
    decorators = mcp_server.find_decorators("07734951", file_path, 6)
    identifiers = mcp_server.find_identifiers("07734951", file_path, 6)
    trace_output_path = mcp_server.trace_identifier_backward("07734951", file_path, 6, "outputPath")
    callers = mcp_server.find_callers("07734951", file_path, "main")
    definition = mcp_server.find_definition("07734951", "main")
    route = mcp_server.find_route_to_function("07734951", "main")

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "  fs.writeFileSync(outputPath, JSON.stringify(config, null, 2), 'utf8');"
    assert imports == []
    assert decorators == []
    assert identifiers == {
        "reads": ["JSON", "config", "fs", "outputPath", "stringify", "writeFileSync"],
        "writes": [],
        "language": "javascript",
    }
    assert trace_output_path == [{"line": 4, "code": "const outputPath = `./output.json`;", "writes": ["outputPath"], "reads": []}]
    assert callers == []
    assert definition == [{"file": file_path, "line": 3, "kind": "function", "snippet": definition[0]["snippet"]}]
    assert route == []


def test_real_finding_new_rule_top_level_write_should_keep_real_flow(monkeypatch, tmp_path):
    source = _fixture_text("cloud_portal/eslint/new-rule.js")
    _write_source_tree(tmp_path, "front_end/eslint-plugin-nx/new-rule.js", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "new-rule.js"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "front_end/eslint-plugin-nx/new-rule.js"
    classification = mcp_server.classify_file("5a36b942", file_path)
    extracted = mcp_server.extract_function("5a36b942", file_path, 6)
    imports = mcp_server.find_imports("5a36b942", file_path)
    decorators = mcp_server.find_decorators("5a36b942", file_path, 6)
    identifiers = mcp_server.find_identifiers("5a36b942", file_path, 6)
    trace_rule_file = mcp_server.trace_identifier_backward("5a36b942", file_path, 6, "ruleFile")

    assert classification["type"] == "production"
    assert extracted["text"] == "// Function not found."
    assert extracted["meta"]["code_on_line"] == "fs.writeFileSync(`./src/rules/${newRuleName}.ts`, ruleFile.replace(/rule-name/g, newRuleName));"
    assert imports == []
    assert decorators == []
    assert identifiers == {
        "reads": ["fs", "newRuleName", "replace", "ruleFile", "writeFileSync"],
        "writes": [],
        "language": "javascript",
    }
    assert trace_rule_file == [{"line": 4, "code": "const ruleFile = 'export default \"rule-name\";';", "writes": ["ruleFile"], "reads": []}]


def test_real_finding_extract_brand_core_values_should_keep_real_flow(monkeypatch, tmp_path):
    source = _fixture_text("cloud_portal/build_scripts/extract_brand_core_values.py")
    _write_source_tree(tmp_path, "build_scripts/extract_brand_core_values.py", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "extract_brand_core_values.py"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "build_scripts/extract_brand_core_values.py"
    classification = mcp_server.classify_file("5a36b942", file_path)
    extracted = mcp_server.extract_function("5a36b942", file_path, 6)
    imports = mcp_server.find_imports("5a36b942", file_path)
    decorators = mcp_server.find_decorators("5a36b942", file_path, 6)
    identifiers = mcp_server.find_identifiers("5a36b942", file_path, 6)
    callers = mcp_server.find_callers("5a36b942", file_path, "main")
    definition = mcp_server.find_definition("5a36b942", "main")
    route = mcp_server.find_route_to_function("5a36b942", "main")

    assert classification["type"] == "config"
    assert extracted["meta"]["code_on_line"] == "    with open(scss_file) as f:"
    assert imports == ["import os", "import re"]
    assert decorators == []
    assert identifiers == {
        "reads": ["open", "re", "read", "scss_file", "search"],
        "writes": ["f"],
        "language": "python",
    }
    assert callers == [{"file": file_path, "line": 14, "caller_function": None, "snippet": callers[0]["snippet"]}]
    assert definition == [{"file": file_path, "line": 5, "kind": "function", "snippet": definition[0]["snippet"]}]
    assert route == []


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the real cloud_portal finding on help/cms/index.html:22. "
        "MCP still rejects .html outright instead of extracting identifiers from the inline script line."
    ),
)
def test_real_finding_help_cms_html_should_support_inline_script_flow(monkeypatch, tmp_path):
    source = _fixture_text("cloud_portal/help/index.html")
    _write_source_tree(tmp_path, "help/cms/index.html", source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "index.html"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    file_path = "help/cms/index.html"
    classification = mcp_server.classify_file("5a36b942", file_path)
    extracted = mcp_server.extract_function("5a36b942", file_path, 4)
    identifiers = mcp_server.find_identifiers("5a36b942", file_path, 4)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == "      document.write(defaulttopic);"
    assert identifiers == {
        "reads": ["document", "defaulttopic", "write"],
        "writes": [],
        "language": "html",
    }


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the live nx-connect-ui pipeline 69ec5b01 on the current container setup. "
        "The full flow fails immediately on classify_file because source-dir resolution raises "
        "'[Errno -2] Name or service not known' before any code/config step can run."
    ),
)
def test_real_finding_live_pipeline_69ec5b01_source_resolution_breaks_flow():
    mcp_server.classify_file(
        "69ec5b01",
        "app/(dashboard)/channel-partners/[id]/components/CompanyAndContactInfo/CompanyAndContactInfo.tsx",
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Validated against the live nx-maps-ui pipeline 07734951 on the current container setup. "
        "The full flow fails immediately on classify_file because source-dir resolution raises "
        "'[Errno -2] Name or service not known' before any code step can run."
    ),
)
def test_real_finding_live_pipeline_07734951_source_resolution_breaks_flow():
    mcp_server.classify_file("07734951", "src/app/auth/oauth/page.tsx")


