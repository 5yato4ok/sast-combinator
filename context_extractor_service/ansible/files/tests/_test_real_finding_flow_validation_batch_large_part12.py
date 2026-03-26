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
    ),
    [
        pytest.param(
            "nx/embed_zip_signature.py",
            "build_utils/code_signing/embed_zip_signature.py",
            12,
            "signature_string_from_file",
            "def signature_string_from_file(prefix, file):",
            {"file", "open"},
            "file",
            11,
            11,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real embed_zip_signature regression: extract_function snaps to the function signature instead of the with-open line.",
            ),
        ),
        pytest.param(
            "nx/signtool_client.py",
            "build_utils/code_signing/signtool_client.py",
            14,
            "main",
            "    args = parser.parse_args()",
            {"args", "client", "load_arguments"},
            "args",
            13,
            5,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real signtool_client regression: extract_function returns parser.parse_args instead of client.load_arguments(args).",
            ),
        ),
        pytest.param(
            "nx/extract_system_data.py",
            "build_utils/customization/extract_system_data.py",
            7,
            "main",
            "    input = json.load(args.source)",
            {"args", "destination", "dump", "json", "systemData"},
            "systemData",
            6,
            4,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real extract_system_data regression: extract_function returns json.load(args.source) instead of json.dump(systemData, args.destination).",
            ),
        ),
        pytest.param(
            "nx/build_analytics_model.py",
            "cloud/ams/analytics_server/deploy/build_analytics_model.py",
            17,
            "prepare_output_dir",
            "    if user_response.lower() == \"y\":",
            {"Path", "directory", "mkdir"},
            "directory",
            11,
            11,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real build_analytics_model regression: extract_function loses the Path(directory).mkdir line entirely.",
            ),
        ),
        pytest.param(
            "nx/build_analytics_model.py",
            "cloud/ams/analytics_server/deploy/build_analytics_model.py",
            24,
            "prepare_json_config",
            '    with open(config_json, "r") as f:',
            {"config_json", "open"},
            "config_json",
            20,
            20,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real build_analytics_model regression: extract_function loses the config_json read line entirely.",
            ),
        ),
        pytest.param(
            "nx/build_analytics_model.py",
            "cloud/ams/analytics_server/deploy/build_analytics_model.py",
            26,
            "prepare_json_config",
            "    config_data[\"classCount\"] = 9",
            {"config_data", "dump", "f", "json"},
            "config_data",
            21,
            20,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real build_analytics_model regression: extract_function returns classCount assignment instead of json.dump(config_data, f, indent=4).",
            ),
        ),
        pytest.param(
            "nx/build_analytics_model.py",
            "cloud/ams/analytics_server/deploy/build_analytics_model.py",
            45,
            "prepare_onnx_model",
            "    if input_model_file.endswith(\".pt\"):",
            {"ValueError", "extension"},
            "extension",
            37,
            36,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real build_analytics_model regression: extract_function snaps to the input_model_file.endswith branch instead of the ValueError line.",
            ),
        ),
        pytest.param(
            "nx/build_analytics_model.py",
            "cloud/ams/analytics_server/deploy/build_analytics_model.py",
            56,
            "prepare_onnx_model",
            "        input_onnx = build_onnx_model(input_pt, output_onnx_path, batch_size)",
            {"batch_size", "build_onnx_model", "input_pt", "output_onnx_path"},
            "input_pt",
            40,
            36,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real build_analytics_model regression: extract_function loses the build_onnx_model assignment line entirely.",
            ),
        ),
    ],
)
def test_real_findings_nx_script_batch_should_keep_full_flow(
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
    assert any(item["file"] == file_path and item["line"] == expected_definition_line for item in definition)
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
    ),
    [
        pytest.param(
            "nx/nx_submodule.py",
            "build_utils/nx_submodule/nx_submodule.py",
            20,
            "main",
            "                parser)",
            {"create_submodule", "nx_submodule_lib"},
            "repo_url",
            15,
            10,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real nx_submodule regression: extract_function expands the _exit call instead of the create_submodule line.",
            ),
        ),
        pytest.param(
            "nx/nx_submodule.py",
            "build_utils/nx_submodule/nx_submodule.py",
            28,
            "main",
            "    else:",
            {"nx_submodule_lib", "update_submodule"},
            "args",
            10,
            10,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real nx_submodule regression: extract_function expands the else/update branch block instead of the update_submodule line.",
            ),
        ),
        pytest.param(
            "nx/nx_submodule.py",
            "build_utils/nx_submodule/nx_submodule.py",
            35,
            "main",
            "            repo_url = _get_repo_url(args)",
            {"find_and_update_submodules", "nx_submodule_lib"},
            "main_repo_dir",
            34,
            10,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real nx_submodule regression: extract_function snaps to repo_url assignment instead of find_and_update_submodules.",
            ),
        ),
        pytest.param(
            "nx/build_analytics_model.py",
            "cloud/ams/analytics_server/deploy/build_analytics_model.py",
            27,
            "build_trt_model",
            "    config_data[\"weightsFile\"] = OUTPUT_TRT_MODEL_NAME",
            {"CUDA_VISIBLE_DEVICES", "env"},
            "env",
            26,
            21,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real build_analytics_model regression: extract_function returns unrelated weightsFile assignment instead of env CUDA_VISIBLE_DEVICES line.",
            ),
        ),
        pytest.param(
            "nx/build_analytics_model.py",
            "cloud/ams/analytics_server/deploy/build_analytics_model.py",
            37,
            "build_trt_model",
            "    print(\"ONNX model built successfully in \" + output_onnx_file)",
            {"run", "subprocess"},
            "tensorrt_path",
            22,
            21,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real build_analytics_model regression: extract_function returns trailing print instead of subprocess.run.",
            ),
        ),
        pytest.param(
            "nx/validate_translations.py",
            "build_utils/translation/validate_translations.py",
            10,
            "validate_file",
            "def validate_file(path):",
            {"ET", "parse", "path"},
            "path",
            9,
            9,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Real validate_translations regression: extract_function snaps to function signature instead of ET.parse(path).",
            ),
        ),
    ],
)
def test_real_findings_nx_submodule_and_translation_batch_should_keep_full_flow(
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
    assert any(item["file"] == file_path and item["line"] == expected_definition_line for item in definition)
    assert route == []


