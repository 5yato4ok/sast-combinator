import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server
from live_mcp_group_audit import _find_callers_oracle_anomalies


def _stub_resolve_source_dir(root: Path):
    def _resolver(_pipeline_id: str) -> Path:
        return root

    return _resolver


def test_find_callers_should_match_oracle_for_simple_javascript_project():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "service.js").write_text(
            "function changePort(port) {\n"
            "  return port;\n"
            "}\n",
        )
        (root / "page.js").write_text(
            "function run() {\n"
            "  changePort('8443');\n"
            "}\n"
            "\n"
            "changePort('9443');\n",
        )

        original = mcp_server._resolve_source_dir
        mcp_server._resolve_source_dir = _stub_resolve_source_dir(root)
        try:
            callers = mcp_server.find_callers("pipe", "service.js", "changePort")
        finally:
            mcp_server._resolve_source_dir = original
        anomalies = _find_callers_oracle_anomalies(root, "changePort", callers)

    assert anomalies == []


def test_find_callers_should_not_confuse_javascript_main_with_unrelated_python_main():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "context-extractor.js").write_text(
            "async function main() {\n"
            "  return true;\n"
            "}\n",
        )
        (root / "runner.js").write_text("main();\n")
        (root / "get_zip_from_cloud.py").write_text(
            "import sys\n"
            "\n"
            "def main(argv):\n"
            "    return argv\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    main(sys.argv[1:])\n",
        )

        original = mcp_server._resolve_source_dir
        mcp_server._resolve_source_dir = _stub_resolve_source_dir(root)
        try:
            callers = mcp_server.find_callers("pipe", "context-extractor.js", "main")
        finally:
            mcp_server._resolve_source_dir = original
        anomalies = _find_callers_oracle_anomalies(root, "main", callers)

    assert anomalies == []


def test_find_callers_should_return_all_typescript_call_sites_with_correct_enclosing_function():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "useScroll.ts").write_text(
            "export function handleScroll() {\n"
            "  return true;\n"
            "}\n",
        )
        (root / "page.ts").write_text(
            "function setup() {\n"
            "  handleScroll();\n"
            "}\n"
            "\n"
            "handleScroll();\n",
        )

        original = mcp_server._resolve_source_dir
        mcp_server._resolve_source_dir = _stub_resolve_source_dir(root)
        try:
            callers = mcp_server.find_callers("pipe", "useScroll.ts", "handleScroll")
        finally:
            mcp_server._resolve_source_dir = original
        anomalies = _find_callers_oracle_anomalies(root, "handleScroll", callers)

    assert anomalies == []


def test_find_callers_should_prefer_real_cpp_constructor_instantiation_over_definition_sites():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "widget.h").write_text(
            "class Widget {\n"
            "public:\n"
            "    Widget();\n"
            "    ~Widget();\n"
            "};\n",
        )
        (root / "widget.cpp").write_text(
            "Widget::Widget() {\n"
            "}\n"
            "\n"
            "Widget::~Widget() {\n"
            "}\n"
            "\n"
            "void run() {\n"
            "  Widget widget;\n"
            "}\n",
        )

        original = mcp_server._resolve_source_dir
        mcp_server._resolve_source_dir = _stub_resolve_source_dir(root)
        try:
            callers = mcp_server.find_callers("pipe", "widget.cpp", "Widget")
        finally:
            mcp_server._resolve_source_dir = original
        anomalies = _find_callers_oracle_anomalies(root, "Widget", callers)

    assert anomalies == []
