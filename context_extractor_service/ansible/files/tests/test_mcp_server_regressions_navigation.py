from _mcp_server_regressions_helpers import *
import pytest
def test_trace_identifier_backward_should_keep_template_literal_reads():
    source = """\
class UriService {
    changePort(newPort: string): void {
        const url = `${newPort}`
        window.location.replace(url)
    }
}
"""
    chain = trace_identifier_backward(source, Path("uri.service.ts"), 4, "url")

    assert chain
    assert "newPort" in chain[0]["reads"]



def test_find_identifiers_should_capture_bindings_inside_multiline_destructured_signature(monkeypatch):
    source = """\
const MapSearch = ({
  systems,
  getLoadedDevices,
  mapCenter,
  deviceCount = 0,
}) => {
  return systems.length
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "MapSearch.tsx"))

    result = mcp_server.find_identifiers("pipe", "MapSearch.tsx", 2)

    assert "systems" in result["writes"]




def test_find_route_to_function_should_ignore_vendor_use_calls_for_generic_symbol_names():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "main.js").write_text("async function main() { return true; }\n")
        (root / "vendor.js").write_text("app.use('/admin', middleware),main=1;\n")

        result = find_route_to_function(root, "main")

    assert result == []


def test_trace_identifier_backward_should_trace_typescript_for_of_bindings():
    source = "for (const item of items) { sink(item) }\n"

    chain = trace_identifier_backward(source, Path("sample.ts"), 1, "item")

    assert chain == [{
        "line": 1,
        "code": "for (const item of items) { sink(item) }",
        "writes": ["item"],
        "reads": ["items", "sink"],
    }]


def test_trace_identifier_backward_should_trace_csharp_foreach_bindings():
    source = "foreach (var item in items) { Sink(item); }\n"

    chain = trace_identifier_backward(source, Path("sample.cs"), 1, "item")

    assert chain == [{
        "line": 1,
        "code": "foreach (var item in items) { Sink(item); }",
        "writes": ["item"],
        "reads": ["Sink", "items"],
    }]


def test_trace_identifier_backward_should_trace_csharp_await_foreach_bindings():
    source = "await foreach (var chunk in request.ReadAllAsync()) { SaveChunk(chunk); }\n"

    chain = trace_identifier_backward(source, Path("sample.cs"), 1, "chunk")

    assert chain == [{
        "line": 1,
        "code": "await foreach (var chunk in request.ReadAllAsync()) { SaveChunk(chunk); }",
        "writes": ["chunk"],
        "reads": ["ReadAllAsync", "SaveChunk", "request"],
    }]


def test_find_route_to_function_should_support_csharp_minimal_api_mapget():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "Program.cs").write_text(
            "app.MapGet(\"/users/{id}\", GetUser);\n"
            "static string GetUser(string id) => LoadUser(id);\n",
        )

        result = find_route_to_function(root, "GetUser")

    assert result == [{
        "file": "Program.cs",
        "line": 1,
        "pattern": "/users/{id}",
        "snippet": ">>>     1| app.MapGet(\"/users/{id}\", GetUser);\n        2| static string GetUser(string id) => LoadUser(id);",
    }]


def test_find_route_to_function_should_support_csharp_minimal_api_mappost():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "Program.cs").write_text(
            "app.MapPost(\"/upload\", UploadAsync);\n"
            "static async Task<IResult> UploadAsync(IFormFile file) => Results.Ok();\n",
        )

        result = find_route_to_function(root, "UploadAsync")

    assert result == [{
        "file": "Program.cs",
        "line": 1,
        "pattern": "/upload",
        "snippet": ">>>     1| app.MapPost(\"/upload\", UploadAsync);\n        2| static async Task<IResult> UploadAsync(IFormFile file) => Results.Ok();",
    }]


def test_trace_identifier_backward_should_trace_csharp_upload_stream_to_file_create():
    source = """\
class UploadController {
  async Task SaveAsync(IFormFile formFile, string path, CancellationToken cancellationToken) {
    await using var stream = File.Create(path);
    await formFile.CopyToAsync(stream, cancellationToken);
  }
}
"""

    chain = trace_identifier_backward(source, Path("UploadController.cs"), 4, "stream")

    assert chain == [{
        "line": 3,
        "code": "await using var stream = File.Create(path);",
        "writes": ["stream"],
        "reads": ["Create", "File", "path"],
    }]


def test_find_route_to_function_should_support_csharp_minimal_api_local_handler():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "Program.cs").write_text(
            "app.MapPost(\"/upload\", UploadAsync);\n"
            "async Task<IResult> UploadAsync(IFormFile file) {\n"
            "  return Results.Ok();\n"
            "}\n",
        )

        result = find_route_to_function(root, "UploadAsync")

    assert result == [{
        "file": "Program.cs",
        "line": 1,
        "pattern": "/upload",
        "snippet": ">>>     1| app.MapPost(\"/upload\", UploadAsync);\n        2| async Task<IResult> UploadAsync(IFormFile file) {",
    }]


def test_trace_identifier_backward_should_trace_csharp_path_combine_before_file_create():
    source = """\
class UploadController {
  async Task SaveAsync(string fileName, CancellationToken cancellationToken) {
    var path = Path.Combine(rootDir, fileName);
    await using var stream = File.Create(path);
    await input.CopyToAsync(stream, cancellationToken);
  }
}
"""

    chain = trace_identifier_backward(source, Path("UploadController.cs"), 5, "path")

    assert chain == [{
        "line": 3,
        "code": "var path = Path.Combine(rootDir, fileName);",
        "writes": ["path"],
        "reads": ["Combine", "Path", "fileName", "rootDir"],
    }]


def test_find_route_to_function_should_support_csharp_minimal_api_inline_lambda_handler():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "Program.cs").write_text(
            "app.MapPost(\"/upload\", async (IFormFile file) => await SaveAsync(file));\n",
        )

        result = find_route_to_function(root, "SaveAsync")

    assert result == [{
        "file": "Program.cs",
        "line": 1,
        "pattern": "/upload",
        "snippet": ">>>     1| app.MapPost(\"/upload\", async (IFormFile file) => await SaveAsync(file));",
    }]


def test_trace_identifier_backward_should_keep_typescript_declaration_trace():
    source = """\
function save(rootDir: string, fileName: string) {
  const path = join(rootDir, fileName);
  upload(path);
}
"""

    chain = trace_identifier_backward(source, Path("save.ts"), 3, "path")

    assert chain == [{
        "line": 2,
        "code": "const path = join(rootDir, fileName);",
        "writes": ["path"],
        "reads": ["fileName", "join", "rootDir"],
    }]


def test_trace_identifier_backward_should_keep_java_declaration_trace():
    source = """\
class UploadController {
  void save(String rootDir, String fileName) {
    String path = join(rootDir, fileName);
    upload(path);
  }
}
"""

    chain = trace_identifier_backward(source, Path("UploadController.java"), 4, "path")

    assert chain == [{
        "line": 3,
        "code": "String path = join(rootDir, fileName);",
        "writes": ["path"],
        "reads": ["fileName", "join", "rootDir"],
    }]


def test_trace_identifier_backward_should_keep_go_short_var_trace():
    source = """\
func save(rootDir string, fileName string) {
    path := join(rootDir, fileName)
    upload(path)
}
"""

    chain = trace_identifier_backward(source, Path("save.go"), 3, "path")

    assert chain == [{
        "line": 2,
        "code": "path := join(rootDir, fileName)",
        "writes": ["path"],
        "reads": ["fileName", "join", "rootDir"],
    }]


def test_trace_identifier_backward_should_keep_python_assignment_trace():
    source = """\
def save(root_dir, file_name):
    path = join(root_dir, file_name)
    upload(path)
"""

    chain = trace_identifier_backward(source, Path("save.py"), 3, "path")

    assert chain == [{
        "line": 2,
        "code": "path = join(root_dir, file_name)",
        "writes": ["path"],
        "reads": ["file_name", "join", "root_dir"],
    }]


def test_trace_identifier_backward_should_trace_typescript_lambda_parameters():
    source = "const run = (url: string) => send(url)\n"

    chain = trace_identifier_backward(source, Path("sample.ts"), 1, "url")

    assert chain == [{
        "line": 1,
        "code": "const run = (url: string) => send(url)",
        "writes": ["url"],
        "reads": ["send"],
    }]


def test_extract_function_should_support_qml_functions(monkeypatch):
    source = """\
Item {
  property string url: backend.baseUrl
  function send(value) {
    Qt.openUrlExternally(url)
  }
}
"""
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "View.qml"))

    result = mcp_server.extract_function("pipe", "View.qml", 4)

    assert result["text"] == "function send(value) {\n    Qt.openUrlExternally(url)\n  }"
    assert result["meta"]["language"] == "qml"
    assert result["meta"]["function_lines"] == (3, 5)


def test_find_definition_should_prefer_typescript_class_field_arrow_definitions():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "api.ts").write_text("class Api {\n  private readonly run = async (u: string) => send(u)\n}\n")
        (root / "main.ts").write_text("callable(() => run(y))\n")

        result = mcp_server._find_definition(root, "run")

    assert result == [{"file": "api.ts", "line": 2, "kind": "function"}]


def test_find_callers_should_support_optional_chained_typescript_calls():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "main.ts").write_text("obj?.send?.(payload)\n")

        result = mcp_server._find_callers(root, "main.ts", "send")

    assert result == [{
        "file": "main.ts",
        "line": 1,
        "caller_function": None,
        "snippet": ">>>     1| obj?.send?.(payload)",
    }]


def test_find_imports_should_raise_on_real_parse_error(monkeypatch):
    source = "function broken( {\n"
    monkeypatch.setattr(mcp_server, "_read_source", _stub_read_source(source, "broken.ts"))

    with pytest.raises(ValueError, match=r"Failed to parse file: broken\.ts"):
        mcp_server.find_imports("pipe", "broken.ts")


def test_trace_identifier_backward_should_raise_on_real_parse_error():
    source = "def broken(:\n    pass\n"

    with pytest.raises(ValueError, match=r"Failed to parse file: broken\.py"):
        trace_identifier_backward(source, Path("broken.py"), 1, "value")
