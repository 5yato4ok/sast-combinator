import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.project_analysis import find_callers


def test_find_callers_should_prefer_real_cpp_invocation_over_definition_and_declaration():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "processor.h").write_text("class DragProcessor { public: void setHandler(int value); };\n")
        (root / "processor.cpp").write_text(
            "void DragProcessor::setHandler(int value) {\n"
            "  (void) value;\n"
            "}\n"
            "\n"
            "void initialize() {\n"
            "  DragProcessor processor;\n"
            "  processor.setHandler(1);\n"
            "}\n",
        )

        callers = find_callers(root, "processor.cpp", "setHandler")

    assert callers
    assert callers[0]["caller_function"] == "initialize"


def test_find_callers_should_not_use_catch_parameter_name_as_caller():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "generate-customization.js").write_text(
            "async function main() {\n"
            "  return true;\n"
            "}\n"
            "\n"
            "main().catch(error => {\n"
            "  console.error(error.message);\n"
            "});\n",
        )

        callers = find_callers(root, "generate-customization.js", "main")

    assert callers
    assert callers[0]["caller_function"] is None


def test_find_callers_should_keep_real_typescript_caller_function():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "service.ts").write_text(
            "export function changePort(newPort: string): void {\n"
            "  return;\n"
            "}\n",
        )
        (root / "page.ts").write_text(
            "function run() {\n"
            "  changePort('8443');\n"
            "}\n",
        )

        callers = find_callers(root, "service.ts", "changePort")

    assert callers
    assert callers[0]["caller_function"] == "run"


def test_find_callers_should_leave_top_level_then_callback_without_fake_caller():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "main.js").write_text(
            "function fetchData() {\n"
            "  return Promise.resolve(true);\n"
            "}\n"
            "\n"
            "fetchData().then((result) => {\n"
            "  console.log(result);\n"
            "});\n",
        )

        callers = find_callers(root, "main.js", "fetchData")

    assert callers
    assert callers[0]["caller_function"] is None
