import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.config import LANG_NODESETS
from context_extractor.identifiers import split_reads_writes
from context_extractor.project_analysis import find_callers, find_definition, find_route_to_function
from context_extractor.project_analysis.shared import _parse_required
from context_extractor.project_analysis.trace import trace_identifier_backward



def test_find_callers_should_not_return_exported_function_definition_as_caller():
    source = """\
import { useState } from 'react';

export default function OAuthDebugPage() {
  const [code, setCode] = useState(null);
  return code;
}
"""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "page.tsx").write_text(source)

        result = find_callers(root, "page.tsx", "OAuthDebugPage")

    assert result == []

def test_find_callers_should_prefer_real_method_invocation_over_definition():
    source_def = """\
export class UriService {
  changePort(newPort: string): void {
    window.location.replace(newPort);
  }
}
"""
    source_use = """\
function run(service) {
  service.changePort('8443');
}
"""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "uri.service.ts").write_text(source_def)
        (root / "page.ts").write_text(source_use)

        result = find_callers(root, "uri.service.ts", "changePort")

    assert result
    assert result[0]["file"] == "page.ts"

def test_find_callers_should_not_treat_cpp_declaration_and_definition_as_callers():
    source_def = """\
class SecuritySettingsWidget {
public:
    void openPixelationConfigurationDialog();
};

void SecuritySettingsWidget::openPixelationConfigurationDialog()
{
    configure();
}
"""
    source_use = """\
void run(SecuritySettingsWidget* widget)
{
    widget->openPixelationConfigurationDialog();
}
"""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "security_settings_widget.cpp").write_text(source_def)
        (root / "other.cpp").write_text(source_use)

        result = find_callers(root, "security_settings_widget.cpp", "openPixelationConfigurationDialog")

    assert result
    assert result[0]["file"] == "other.cpp"

def test_find_callers_should_report_enclosing_javascript_function_name_for_callback_invocations():
    source = """\
async function setPreviewState(asset_id, create_id, el, state) {
    const params = new URLSearchParams(window.location.search);
    return state;
}

function bindSelects() {
    const selectElements = $('.field-asset select');
    selectElements.each(function (index) {
        const val = $(this).children("option:selected").val();
        setPreviewState(val, false, this);
    });
}
"""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "menuChange.js").write_text(source)

        result = find_callers(root, "menuChange.js", "setPreviewState")

    assert result
    assert result[0]["caller_function"] == "bindSelects"



def test_find_callers_should_not_use_catch_parameter_name_as_caller_function():
    source = """\
async function main() {
    console.log('Starting');
}

main().catch(error => {
    console.error(error.message);
});
"""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "generate-customization.js").write_text(source)

        result = find_callers(root, "generate-customization.js", "main")

    assert result
    assert result[0]["caller_function"] is None


def test_find_callers_should_leave_top_level_promise_then_without_fake_caller_name():
    source = """\
function fetchData() {
    return Promise.resolve(1);
}

fetchData().then((result) => {
    console.log(result);
});
"""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "sample.js").write_text(source)

        result = find_callers(root, "sample.js", "fetchData")

    assert result
    assert result[0]["caller_function"] is None


def test_find_callers_should_leave_event_listener_callback_invocation_without_fake_caller_name():
    source = """\
function handle() {
    return true;
}
window.addEventListener('click', () => {
    handle();
});
"""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "sample.js").write_text(source)

        result = find_callers(root, "sample.js", "handle")

    assert result
    assert result[0]["caller_function"] is None


def test_find_callers_should_return_all_typescript_callers_across_subdirectories():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src/a").mkdir(parents=True, exist_ok=True)
        (root / "src/b").mkdir(parents=True, exist_ok=True)
        (root / "src/c/nested").mkdir(parents=True, exist_ok=True)
        (root / "src/a/service.ts").write_text(
            "export const send = (cb: () => void) => cb()\n",
        )
        (root / "src/b/feature.ts").write_text(
            "import { send } from '../a/service'\n"
            "function run() {\n"
            "  send(() => work(x))\n"
            "}\n",
        )
        (root / "src/c/nested/worker.ts").write_text(
            "function boot() {\n"
            "  obj?.send?.(payload)\n"
            "}\n",
        )

        result = find_callers(root, "src/a/service.ts", "send")

    assert result == [
        {
            "file": "src/b/feature.ts",
            "line": 3,
            "caller_function": "run",
            "snippet": "        2| function run() {\n>>>     3|   send(() => work(x))\n        4| }",
        },
        {
            "file": "src/c/nested/worker.ts",
            "line": 2,
            "caller_function": "boot",
            "snippet": "        1| function boot() {\n>>>     2|   obj?.send?.(payload)\n        3| }",
        },
    ]


def test_find_callers_should_support_csharp_calls_inside_lambda_arguments():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "service.cs").write_text("class Sender { void send(int value) {} }\n")
        (root / "runner.cs").write_text(
            "using System.Linq;\n"
            "class Runner {\n"
            "  void Boot() {\n"
            "    items.Select(x => send(x)).ToList();\n"
            "  }\n"
            "}\n",
        )

        result = find_callers(root, "service.cs", "send")

    assert result == [
        {
            "file": "runner.cs",
            "line": 4,
            "caller_function": "Boot",
            "snippet": "        3|   void Boot() {\n>>>     4|     items.Select(x => send(x)).ToList();\n        5|   }",
        }
    ]


def test_find_definition_should_support_csharp_expression_bodied_methods():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "runner.cs").write_text(
            "class Runner {\n"
            "  int Map(int x) => Transform(x);\n"
            "}\n",
        )

        result = find_definition(root, "Map")

    assert result == [{"file": "runner.cs", "line": 2, "kind": "function"}]


def test_find_definition_should_prefer_typescript_overload_implementation():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "api.ts").write_text(
            "function fetcher(x: string): string;\n"
            "function fetcher(x: number): number;\n"
            "function fetcher(x: string | number) { return x; }\n",
        )

        result = find_definition(root, "fetcher")

    assert result == [{"file": "api.ts", "line": 3, "kind": "function"}]


def test_find_definition_should_treat_csharp_delegate_fields_as_callable_definitions():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "runner.cs").write_text(
            "using System;\n"
            "class Runner {\n"
            "  Func<int, int> transform = x => Send(x);\n"
            "}\n",
        )

        result = find_definition(root, "transform")

    assert result == [{"file": "runner.cs", "line": 3, "kind": "function"}]


def test_find_callers_should_support_typescript_class_field_arrow_this_calls():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "api.ts").write_text(
            "class Api {\n"
            "  private readonly run = async (u: string) => send(u);\n"
            "  method() {\n"
            "    this.run(url);\n"
            "  }\n"
            "}\n",
        )

        result = find_callers(root, "api.ts", "run")

    assert result == [
        {
            "file": "api.ts",
            "line": 4,
            "caller_function": "method",
            "snippet": "        3|   method() {\n>>>     4|     this.run(url);\n        5|   }",
        }
    ]


def test_find_callers_should_support_typescript_nested_member_chain_calls():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "api.ts").write_text(
            "export class Api {\n"
            "  private readonly run = async (u: string) => send(u);\n"
            "}\n",
        )
        (root / "worker.ts").write_text(
            "function boot() {\n"
            "  obj.service.run(payload);\n"
            "}\n",
        )

        result = find_callers(root, "api.ts", "run")

    assert result == [
        {
            "file": "worker.ts",
            "line": 2,
            "caller_function": "boot",
            "snippet": "        1| function boot() {\n>>>     2|   obj.service.run(payload);\n        3| }",
        }
    ]


def test_trace_identifier_backward_should_support_csharp_implicit_lambda_parameters():
    source = """\
class Runner {
  void Boot() {
    items.Select(x => {
      return Send(x);
    }).ToList();
  }
}
"""

    chain = trace_identifier_backward(source, Path("runner.cs"), 4, "x")

    assert chain == [{
        "line": 3,
        "code": "items.Select(x => {",
        "writes": ["x"],
        "reads": ["Send"],
    }]


def test_find_definition_should_support_csharp_property_accessors():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "runner.cs").write_text(
            "class Runner {\n"
            "  string Token { get => BuildToken(); }\n"
            "}\n",
        )

        result = find_definition(root, "Token")

    assert result == [{"file": "runner.cs", "line": 2, "kind": "function"}]


def test_find_callers_should_support_csharp_constructor_object_creation():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "foo.cs").write_text("class Foo { public Foo(int bar) {} }\n")
        (root / "runner.cs").write_text(
            "class Runner {\n"
            "  void Boot() {\n"
            "    var foo = new Foo(bar);\n"
            "  }\n"
            "}\n",
        )

        result = find_callers(root, "foo.cs", "Foo")

    assert result == [
        {
            "file": "runner.cs",
            "line": 3,
            "caller_function": "Boot",
            "snippet": "        2|   void Boot() {\n>>>     3|     var foo = new Foo(bar);\n        4|   }",
        }
    ]


def test_find_definition_should_support_csharp_indexer_declarations():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "buffer.cs").write_text(
            "class Buffer {\n"
            "  int this[int i] => data[i];\n"
            "}\n",
        )

        result = find_definition(root, "this")

    assert result == [{"file": "buffer.cs", "line": 2, "kind": "function"}]


def test_trace_identifier_backward_should_support_csharp_anonymous_method_parameters():
    source = """\
class Runner {
  void Boot() {
    items.Select(delegate(int x) {
      return Send(x);
    });
  }
}
"""

    chain = trace_identifier_backward(source, Path("runner.cs"), 4, "x")

    assert chain == [{
        "line": 3,
        "code": "items.Select(delegate(int x) {",
        "writes": ["x"],
        "reads": ["Send"],
    }]


def test_find_definition_should_support_csharp_operator_declarations():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "money.cs").write_text(
            "class Money {\n"
            "  public static Money operator +(Money left, Money right) => left;\n"
            "}\n",
        )

        result = find_definition(root, "operator+")

    assert result == [{"file": "money.cs", "line": 2, "kind": "function"}]


def test_find_definition_should_support_csharp_delegate_declarations():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "notify.cs").write_text(
            "public delegate void Notify(string value);\n",
        )

        result = find_definition(root, "Notify")

    assert result == [{"file": "notify.cs", "line": 1, "kind": "function"}]


def test_find_identifiers_should_support_csharp_conditional_and_element_access():
    source = """\
class Runner {
  void Boot() {
    sink(client?.Config[key]);
  }
}
    """

    tree, lang_key, src_bytes = _parse_required(source, Path("runner.cs"))
    stack = [tree.root_node]
    stmt = None
    while stack:
        node = stack.pop()
        if node.type == "expression_statement":
            stmt = node
            break
        stack.extend(reversed(node.children))

    assert stmt is not None
    reads, writes = split_reads_writes(stmt, src_bytes, lang_key, LANG_NODESETS[lang_key])

    assert sorted(reads) == ["Config", "client", "key", "sink"]
    assert writes == set()


def test_find_callers_should_support_cpp_member_calls_inside_lambda_bodies():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "service.cpp").write_text("void send(int payload) {}\n")
        (root / "worker.cpp").write_text(
            "void boot() {\n"
            "  auto fn = [&]() {\n"
            "    client.send(payload);\n"
            "  };\n"
            "  fn();\n"
            "}\n",
        )

        result = find_callers(root, "service.cpp", "send")

    assert result == [
        {
            "file": "worker.cpp",
            "line": 3,
            "caller_function": "boot",
            "snippet": "        2|   auto fn = [&]() {\n>>>     3|     client.send(payload);\n        4|   };",
        }
    ]


def test_find_definition_should_support_cpp_subscript_operator_definitions():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "buffer.cpp").write_text(
            "class Buffer {\n"
            "public:\n"
            "  int operator[](int index) const;\n"
            "};\n\n"
            "int Buffer::operator[](int index) const {\n"
            "  return data[index];\n"
            "}\n",
        )

        result = find_definition(root, "operator[]")

    assert result == [{"file": "buffer.cpp", "line": 6, "kind": "function"}]


def test_find_definition_should_support_cpp_call_operator_definitions():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "handler.cpp").write_text(
            "class Handler {\n"
            "public:\n"
            "  void operator()(int payload) const;\n"
            "};\n\n"
            "void Handler::operator()(int payload) const {\n"
            "  sink(payload);\n"
            "}\n",
        )

        result = find_definition(root, "operator()")

    assert result == [{"file": "handler.cpp", "line": 6, "kind": "function"}]


def test_find_callers_should_support_cpp_callable_object_invocations():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "handler.cpp").write_text(
            "class Handler {\n"
            "public:\n"
            "  void operator()(int payload) const;\n"
            "};\n\n"
            "void Handler::operator()(int payload) const {\n"
            "  sink(payload);\n"
            "}\n",
        )
        (root / "worker.cpp").write_text(
            "void boot() {\n"
            "  Handler handler;\n"
            "  handler(payload);\n"
            "}\n",
        )

        result = find_callers(root, "handler.cpp", "operator()")

    assert result == [
        {
            "file": "worker.cpp",
            "line": 3,
            "caller_function": "boot",
            "snippet": "        2|   Handler handler;\n>>>     3|   handler(payload);\n        4| }",
        }
    ]


def test_find_callers_should_report_qml_signal_handler_as_caller_function():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "View.qml").write_text(
            "Item {\n"
            "  property string url: backend.baseUrl\n"
            "  MouseArea {\n"
            "    onClicked: Qt.openUrlExternally(url)\n"
            "  }\n"
            "}\n",
        )

        result = find_callers(root, "View.qml", "openUrlExternally")

    assert result == [
        {
            "file": "View.qml",
            "line": 4,
            "caller_function": "onClicked",
            "snippet": "        3|   MouseArea {\n>>>     4|     onClicked: Qt.openUrlExternally(url)\n        5|   }",
        }
    ]


def test_find_definition_should_treat_qml_signal_handler_binding_as_callable_definition():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "View.qml").write_text(
            "Item {\n"
            "  MouseArea {\n"
            "    onClicked: Qt.openUrlExternally(url)\n"
            "  }\n"
            "}\n",
        )

        result = find_definition(root, "onClicked")

    assert result == [{"file": "View.qml", "line": 3, "kind": "function"}]


def test_find_callers_and_definition_should_support_qml_attached_signal_handlers():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "View.qml").write_text(
            "Item {\n"
            "  Component.onCompleted: Qt.quit()\n"
            "}\n",
        )

        callers = find_callers(root, "View.qml", "quit")
        definition = find_definition(root, "onCompleted")

    assert callers == [
        {
            "file": "View.qml",
            "line": 2,
            "caller_function": "Component.onCompleted",
            "snippet": "        1| Item {\n>>>     2|   Component.onCompleted: Qt.quit()\n        3| }",
        }
    ]
    assert definition == [{"file": "View.qml", "line": 2, "kind": "function"}]


def test_find_callers_should_support_qml_connections_handler_functions():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "View.qml").write_text(
            "Item {\n"
            "  Connections {\n"
            "    target: backend\n"
            "    function onReady(value) {\n"
            "      console.log(value)\n"
            "    }\n"
            "  }\n"
            "}\n",
        )

        result = find_callers(root, "View.qml", "log")

    assert result == [
        {
            "file": "View.qml",
            "line": 5,
            "caller_function": "onReady",
            "snippet": "        4|     function onReady(value) {\n>>>     5|       console.log(value)\n        6|     }",
        }
    ]


def test_trace_identifier_backward_should_support_qml_property_bindings():
    source = """\
Item {
  property string url: backend.baseUrl
}
"""

    chain = trace_identifier_backward(source, Path("View.qml"), 2, "url")

    assert chain == [{
        "line": 2,
        "code": "property string url: backend.baseUrl",
        "writes": ["url"],
        "reads": ["backend", "baseUrl"],
    }]


def test_project_navigation_should_support_multimodule_typescript_triage_flow():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src/api").mkdir(parents=True, exist_ok=True)
        (root / "src/services").mkdir(parents=True, exist_ok=True)
        (root / "src/utils").mkdir(parents=True, exist_ok=True)
        (root / "src/other").mkdir(parents=True, exist_ok=True)

        (root / "src/api/routes.ts").write_text(
            "import { uploadAvatar } from '../services/uploadService'\n"
            "app.post('/upload/avatar', uploadAvatar)\n",
        )
        (root / "src/services/uploadService.ts").write_text(
            "import { buildUploadPath } from '../utils/pathBuilder'\n"
            "import { writeFile } from '../utils/storage'\n"
            "export async function uploadAvatar(fileName: string, body: string) {\n"
            "  const path = buildUploadPath(fileName)\n"
            "  return writeFile(path, body)\n"
            "}\n",
        )
        (root / "src/utils/pathBuilder.ts").write_text(
            "export function buildUploadPath(fileName: string) {\n"
            "  return join(baseDir, fileName)\n"
            "}\n",
        )
        (root / "src/utils/storage.ts").write_text(
            "export async function writeFile(path: string, body: string) {\n"
            "  return fs.writeFile(path, body)\n"
            "}\n",
        )
        (root / "src/other/routes.ts").write_text(
            "app.post('/noise', unrelated)\n"
            "function unrelated() { return true }\n",
        )
        (root / "src/other/uploadService.ts").write_text(
            "export function uploadAvatar() { return noop() }\n",
        )

        route = find_route_to_function(root, "uploadAvatar")
        definition = find_definition(root, "buildUploadPath")
        callers = find_callers(root, "src/utils/pathBuilder.ts", "buildUploadPath")

    assert route == [{
        "file": "src/api/routes.ts",
        "line": 2,
        "pattern": "/upload/avatar",
        "snippet": "        1| import { uploadAvatar } from '../services/uploadService'\n>>>     2| app.post('/upload/avatar', uploadAvatar)",
    }]
    assert definition == [{"file": "src/utils/pathBuilder.ts", "line": 1, "kind": "function"}]
    assert callers == [{
        "file": "src/services/uploadService.ts",
        "line": 4,
        "caller_function": "uploadAvatar",
        "snippet": "        3| export async function uploadAvatar(fileName: string, body: string) {\n>>>     4|   const path = buildUploadPath(fileName)\n        5|   return writeFile(path, body)",
    }]


def test_project_navigation_should_support_multimodule_python_triage_flow():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "api").mkdir(parents=True, exist_ok=True)
        (root / "services").mkdir(parents=True, exist_ok=True)
        (root / "utils").mkdir(parents=True, exist_ok=True)
        (root / "other").mkdir(parents=True, exist_ok=True)

        (root / "api/urls.py").write_text(
            "from services.upload_service import upload_avatar\n"
            "urlpatterns = [path('upload/avatar', upload_avatar)]\n",
        )
        (root / "services/upload_service.py").write_text(
            "from utils.path_builder import build_upload_path\n"
            "from utils.storage import write_file\n"
            "def upload_avatar(file_name, body):\n"
            "    path = build_upload_path(file_name)\n"
            "    return write_file(path, body)\n",
        )
        (root / "utils/path_builder.py").write_text(
            "def build_upload_path(file_name):\n"
            "    return join(base_dir, file_name)\n",
        )
        (root / "utils/storage.py").write_text(
            "def write_file(path, body):\n"
            "    return open(path, 'w').write(body)\n",
        )
        (root / "other/urls.py").write_text(
            "urlpatterns = [path('noise', other_view)]\n",
        )
        (root / "other/upload_service.py").write_text(
            "def upload_avatar():\n"
            "    return noop()\n",
        )

        route = find_route_to_function(root, "upload_avatar")
        definition = find_definition(root, "build_upload_path")
        callers = find_callers(root, "utils/path_builder.py", "build_upload_path")

    assert route == [{
        "file": "api/urls.py",
        "line": 2,
        "pattern": "upload/avatar",
        "snippet": "        1| from services.upload_service import upload_avatar\n>>>     2| urlpatterns = [path('upload/avatar', upload_avatar)]",
    }]
    assert definition == [{"file": "utils/path_builder.py", "line": 1, "kind": "function"}]
    assert callers == [{
        "file": "services/upload_service.py",
        "line": 4,
        "caller_function": "upload_avatar",
        "snippet": "        3| def upload_avatar(file_name, body):\n>>>     4|     path = build_upload_path(file_name)\n        5|     return write_file(path, body)",
    }]


def test_project_navigation_should_support_noisy_multimodule_typescript_triage_flow():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel in [
            "src/api", "src/controllers", "src/services", "src/utils",
            "src/admin", "src/tests", "src/legacy", "src/feature/nested",
        ]:
            (root / rel).mkdir(parents=True, exist_ok=True)

        (root / "src/api/routes.ts").write_text(
            "import { handleUpload } from '../controllers/uploadController'\n"
            "app.post('/v1/upload', handleUpload)\n",
        )
        (root / "src/controllers/uploadController.ts").write_text(
            "import { persistUpload } from '../services/uploadService'\n"
            "export async function handleUpload(fileName: string, body: string) {\n"
            "  return persistUpload(fileName, body)\n"
            "}\n",
        )
        (root / "src/services/uploadService.ts").write_text(
            "import { buildUploadPath } from '../utils/pathBuilder'\n"
            "import { writeFile } from '../utils/storage'\n"
            "export async function persistUpload(fileName: string, body: string) {\n"
            "  const path = buildUploadPath(fileName)\n"
            "  return writeFile(path, body)\n"
            "}\n",
        )
        (root / "src/utils/pathBuilder.ts").write_text(
            "export function buildUploadPath(fileName: string) {\n"
            "  return join(baseDir, fileName)\n"
            "}\n",
        )
        (root / "src/utils/storage.ts").write_text(
            "export async function writeFile(path: string, body: string) {\n"
            "  return fs.writeFile(path, body)\n"
            "}\n",
        )

        (root / "src/admin/routes.ts").write_text(
            "app.post('/admin/upload', adminUpload)\n",
        )
        (root / "src/admin/uploadController.ts").write_text(
            "export function adminUpload() { return auditOnly() }\n",
        )
        (root / "src/legacy/uploadService.ts").write_text(
            "export function legacyPersistUpload() { return noop() }\n",
        )
        (root / "src/tests/pathBuilder.ts").write_text(
            "export function buildUploadPath() { return '/tmp/test' }\n",
        )
        (root / "src/feature/nested/storage.ts").write_text(
            "export function writeFile() { return memoryStore() }\n",
        )

        route = find_route_to_function(root, "handleUpload")
        definition = find_definition(root, "persistUpload")
        callers = find_callers(root, "src/services/uploadService.ts", "persistUpload")

    assert route == [{
        "file": "src/api/routes.ts",
        "line": 2,
        "pattern": "/v1/upload",
        "snippet": "        1| import { handleUpload } from '../controllers/uploadController'\n>>>     2| app.post('/v1/upload', handleUpload)",
    }]
    assert definition == [{"file": "src/services/uploadService.ts", "line": 3, "kind": "function"}]
    assert callers == [{
        "file": "src/controllers/uploadController.ts",
        "line": 3,
        "caller_function": "handleUpload",
        "snippet": "        2| export async function handleUpload(fileName: string, body: string) {\n>>>     3|   return persistUpload(fileName, body)\n        4| }",
    }]


def test_project_navigation_should_support_noisy_multimodule_csharp_triage_flow():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel in [
            "Api", "Controllers", "Services", "Utils",
            "Admin", "Legacy", "Tests", "Feature/Nested",
        ]:
            (root / rel).mkdir(parents=True, exist_ok=True)

        (root / "Api/Routes.cs").write_text(
            "app.MapPost(\"/v1/upload\", HandleUpload);\n",
        )
        (root / "Controllers/UploadController.cs").write_text(
            "class UploadController {\n"
            "  static Task<IResult> HandleUpload(string fileName, string body) {\n"
            "    return UploadService.PersistUpload(fileName, body);\n"
            "  }\n"
            "}\n",
        )
        (root / "Services/UploadService.cs").write_text(
            "class UploadService {\n"
            "  static Task<IResult> PersistUpload(string fileName, string body) {\n"
            "    var path = BuildUploadPath(fileName);\n"
            "    return WriteFile(path, body);\n"
            "  }\n"
            "}\n",
        )
        (root / "Utils/PathBuilder.cs").write_text(
            "class PathBuilder {\n"
            "  static string BuildUploadPath(string fileName) => Path.Combine(baseDir, fileName);\n"
            "}\n",
        )
        (root / "Utils/Storage.cs").write_text(
            "class Storage {\n"
            "  static Task WriteFile(string path, string body) => File.WriteAllTextAsync(path, body);\n"
            "}\n",
        )

        (root / "Admin/Routes.cs").write_text(
            "app.MapPost(\"/admin/upload\", AdminHandleUpload);\n",
        )
        (root / "Admin/UploadController.cs").write_text(
            "class UploadController { static IResult AdminHandleUpload() => Results.Ok(); }\n",
        )
        (root / "Legacy/UploadService.cs").write_text(
            "class UploadService { static IResult LegacyPersistUpload() => Results.Ok(); }\n",
        )
        (root / "Tests/PathBuilder.cs").write_text(
            "class PathBuilder { static string BuildUploadPath() => \"/tmp/test\"; }\n",
        )
        (root / "Feature/Nested/Storage.cs").write_text(
            "class Storage { static void WriteFile() {} }\n",
        )

        route = find_route_to_function(root, "HandleUpload")
        definition = find_definition(root, "PersistUpload")
        callers = find_callers(root, "Services/UploadService.cs", "PersistUpload")

    assert route == [{
        "file": "Api/Routes.cs",
        "line": 1,
        "pattern": "/v1/upload",
        "snippet": ">>>     1| app.MapPost(\"/v1/upload\", HandleUpload);",
    }]
    assert definition == [{"file": "Services/UploadService.cs", "line": 2, "kind": "function"}]
    assert callers == [{
        "file": "Controllers/UploadController.cs",
        "line": 3,
        "caller_function": "HandleUpload",
        "snippet": "        2|   static Task<IResult> HandleUpload(string fileName, string body) {\n>>>     3|     return UploadService.PersistUpload(fileName, body);\n        4|   }",
    }]
