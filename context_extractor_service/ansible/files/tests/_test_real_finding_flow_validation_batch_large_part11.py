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
            "nx/generic_http_signing_client.py",
            "build_utils/code_signing/generic_http_signing_client.py",
            15,
            "upload",
            "        session.mount(self.url, HTTPAdapter(max_retries=retries))",
            {"get", "self", "session", "url"},
            "session",
            13,
            11,
            "function",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real generic_http_signing_client regression: extract_function returns the session.mount line instead of session.get(self.url).",
            ),
        ),
        pytest.param(
            "nx/generic_http_signing_client.py",
            "build_utils/code_signing/generic_http_signing_client.py",
            19,
            "upload",
            "        try:",
            {"file_handle", "post", "self", "session"},
            "file_handle",
            18,
            11,
            "function",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real generic_http_signing_client regression: extract_function expands the try/with block instead of the session.post line.",
            ),
        ),
        pytest.param(
            "nx/validate_jsons.py",
            "build_utils/python/validate_jsons.py",
            11,
            "validate_jsons",
            "            if fnmatch(name, pattern):",
            {"PIPE", "Popen", "fnmatch", "name", "os", "path", "subprocess"},
            "path",
            7,
            7,
            "function",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real validate_jsons regression: extract_function snaps to the fnmatch guard instead of the subprocess.Popen line.",
            ),
        ),
        pytest.param(
            "nx/replace_in_file.py",
            "build_utils/replace_in_file.py",
            11,
            "replace_in_file",
            '        with open(file_name, "wb") as f:',
            {"file_name", "open"},
            "file_name",
            5,
            1,
            "function",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real replace_in_file regression: extract_function loses the second with-open line and returns empty code_on_line.",
            ),
        ),
    ],
)
def test_real_findings_nx_build_utils_batch_should_keep_full_flow(
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

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, line_number)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, line_number)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, line_number)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, line_number, trace_symbol)
    callers = mcp_server.find_callers("9ce90895", file_path, function_name)
    definition = mcp_server.find_definition("9ce90895", function_name)
    route = mcp_server.find_route_to_function("9ce90895", function_name)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == expected_line
    assert isinstance(imports, list)
    assert decorators == []
    assert identifiers["language"] == "python"
    assert reads_subset.issubset(set(identifiers["reads"]))
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
            "nx/email_preprocess.py",
            "build_utils/email_templates/preprocess.py",
            5,
            "generate_file",
            "def generate_file(source_file: Path, target_file: Path, transformer):",
            {"open", "read", "source_file"},
            "source_file",
            4,
            4,
            "function",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real email preprocess regression: extract_function snaps to the function signature instead of the source_file open/read line.",
            ),
        ),
        pytest.param(
            "nx/email_preprocess.py",
            "build_utils/email_templates/preprocess.py",
            10,
            "generate_file",
            '    with open(target_file, \'w\', encoding="utf-8", newline=\'\\n\') as f:',
            {"open", "target_file"},
            "target_file",
            4,
            4,
            "function",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real email preprocess regression: extract_function returns target_file.parent.mkdir instead of the target_file open/write line.",
            ),
        ),
        pytest.param(
            "nx/clear_cmake_build.py",
            "build_utils/python/clear_cmake_build.py",
            14,
            "delete_path",
            "        shutil.rmtree(path)",
            {"path", "rmtree", "shutil"},
            "path",
            8,
            8,
            "function",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real clear_cmake_build regression: extract_function loses the shutil.rmtree branch line entirely.",
            ),
        ),
        pytest.param(
            "nx/clear_cmake_build.py",
            "build_utils/python/clear_cmake_build.py",
            14,
            "delete_path",
            "        shutil.rmtree(path)",
            {"os", "path", "remove"},
            "path",
            8,
            8,
            "function",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real clear_cmake_build regression: extract_function returns the shutil.rmtree branch instead of the os.remove branch line.",
            ),
        ),
        pytest.param(
            "nx/update_translations.py",
            "build_utils/translation/update_translations.py",
            12,
            "update_translations",
            "    entries = calculateEntries(filename, translationDir, language)",
            {"lupdate"},
            "lupdate",
            7,
            7,
            "function",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real update_translations regression: extract_function snaps to entries calculation instead of the command initialization line.",
            ),
        ),
    ],
)
def test_real_findings_nx_more_build_utils_batch_should_keep_full_flow(
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

    classification = mcp_server.classify_file("9ce90895", file_path)
    extracted = mcp_server.extract_function("9ce90895", file_path, line_number)
    imports = mcp_server.find_imports("9ce90895", file_path)
    decorators = mcp_server.find_decorators("9ce90895", file_path, line_number)
    identifiers = mcp_server.find_identifiers("9ce90895", file_path, line_number)
    trace = mcp_server.trace_identifier_backward("9ce90895", file_path, line_number, trace_symbol)
    callers = mcp_server.find_callers("9ce90895", file_path, function_name)
    definition = mcp_server.find_definition("9ce90895", function_name)
    route = mcp_server.find_route_to_function("9ce90895", function_name)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == expected_line
    assert isinstance(imports, list)
    assert decorators == []
    assert identifiers["language"] == "python"
    assert reads_subset.issubset(set(identifiers["reads"]))
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
        "fixture_path",
        "line_number",
        "function_name",
        "expected_line",
        "reads_subset",
        "trace_symbol",
        "expected_trace_line",
        "expected_definition_line",
    ),
    [
        pytest.param(
            "cloud_portal/git_operations_debug.js",
            13,
            "detectBranchPoint",
            "        console.error(`Detecting branch point for: ${currentBranch}`);",
            {"console", "currentBranch", "error"},
            "currentBranch",
            11,
            9,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real git-operations regression: extract_function snaps to the DEBUG guard instead of the branch-point detection logger line.",
            ),
        ),
        pytest.param(
            "cloud_portal/git_operations_debug.js",
            32,
            "detectBranchPoint",
            "        console.error('Error detecting branch point:', error);",
            {"console", "error"},
            "error",
            None,
            9,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real git-operations regression: extract_function returns the thrown error line instead of the branch-point error logger line.",
            ),
        ),
        pytest.param(
            "cloud_portal/git_operations_debug.js",
            55,
            "runCommandWithRetry",
            "          console.error(`Attempt ${attempt} failed for command: ${command.substring(0, 50)}...`);",
            {"attempt", "command", "console", "error", "substring"},
            "attempt",
            38,
            37,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real git-operations regression: extract_function loses the retry-attempt logger line entirely.",
            ),
        ),
        pytest.param(
            "cloud_portal/git_operations_debug.js",
            56,
            "runCommandWithRetry",
            "          console.error(`Retrying in ${delay}ms...`);",
            {"console", "delay", "error"},
            "delay",
            53,
            37,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real git-operations regression: extract_function snaps to the terminal retry guard instead of the retry-delay logger line.",
            ),
        ),
    ],
)
def test_real_findings_cloud_portal_git_operations_batch_should_keep_full_flow(
    monkeypatch,
    fixture_path,
    line_number,
    function_name,
    expected_line,
    reads_subset,
    trace_symbol,
    expected_trace_line,
    expected_definition_line,
    tmp_path,
):
    file_path = ".github/chatmodes/modules/git-operations.js"
    source = _fixture_text(fixture_path)
    _write_source_tree(tmp_path, file_path, source)
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "git-operations.js"))
    monkeypatch.setattr(mcp_server, "_resolve_source_dir", lambda _pipeline_id: tmp_path)

    classification = mcp_server.classify_file("5a36b942", file_path)
    extracted = mcp_server.extract_function("5a36b942", file_path, line_number)
    imports = mcp_server.find_imports("5a36b942", file_path)
    decorators = mcp_server.find_decorators("5a36b942", file_path, line_number)
    identifiers = mcp_server.find_identifiers("5a36b942", file_path, line_number)
    trace = mcp_server.trace_identifier_backward("5a36b942", file_path, line_number, trace_symbol)
    callers = mcp_server.find_callers("5a36b942", file_path, function_name)
    definition = mcp_server.find_definition("5a36b942", function_name)
    route = mcp_server.find_route_to_function("5a36b942", function_name)

    assert classification["type"] == "production"
    assert extracted["meta"]["code_on_line"] == expected_line
    assert isinstance(imports, list)
    assert decorators == []
    assert identifiers["language"] == "javascript"
    assert reads_subset.issubset(set(identifiers["reads"]))
    if expected_trace_line is None:
        assert isinstance(trace, list)
    else:
        assert trace
        assert trace[0]["line"] == expected_trace_line
    assert isinstance(callers, list)
    assert any(item["file"] == file_path and item["line"] == expected_definition_line for item in definition)
    assert route == []


