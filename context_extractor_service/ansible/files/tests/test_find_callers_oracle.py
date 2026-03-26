import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from live_mcp_group_audit import _expected_callers, _find_callers_oracle_anomalies


def test_expected_callers_should_collect_all_real_javascript_call_sites():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "service.js").write_text(
            "function changePort(newPort) {\n"
            "  return newPort;\n"
            "}\n",
        )
        (root / "page.js").write_text(
            "function run() {\n"
            "  changePort('8443');\n"
            "}\n"
            "\n"
            "changePort('9443');\n",
        )

        callers = _expected_callers(root, "changePort")

    assert callers == [
        {"file": "page.js", "line": 2, "caller_function": "run"},
        {"file": "page.js", "line": 5, "caller_function": None},
    ]


def test_expected_callers_should_skip_definition_and_forward_declaration_sites():
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

        callers = _expected_callers(root, "setHandler")

    assert callers == [
        {"file": "processor.cpp", "line": 7, "caller_function": "initialize"},
    ]


def test_find_callers_oracle_anomalies_should_detect_missing_and_mismatched_callers():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "page.js").write_text(
            "function run() {\n"
            "  changePort('8443');\n"
            "}\n"
            "\n"
            "changePort('9443');\n",
        )

        payload = [
            {"file": "page.js", "line": 2, "caller_function": "wrong"},
        ]
        anomalies = _find_callers_oracle_anomalies(root, "changePort", payload)

    assert "caller_missing_expected" in anomalies
    assert "caller_enclosing_mismatch" in anomalies


def test_find_callers_oracle_anomalies_should_detect_unexpected_extra_callers():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "page.js").write_text(
            "function run() {\n"
            "  changePort('8443');\n"
            "}\n",
        )

        payload = [
            {"file": "page.js", "line": 2, "caller_function": "run"},
            {"file": "other.js", "line": 1, "caller_function": None},
        ]
        anomalies = _find_callers_oracle_anomalies(root, "changePort", payload)

    assert "caller_extra_unexpected" in anomalies
