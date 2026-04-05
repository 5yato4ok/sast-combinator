import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.project_analysis import find_callers, find_definition, find_route_to_function


def test_find_route_to_function_should_keep_real_express_route_hit():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "api.js").write_text(
            "app.get('/health', healthCheck)\n"
            "function healthCheck(req, res) { return res; }\n",
        )

        routes = find_route_to_function(root, "healthCheck")

    assert routes
    assert routes[0]["pattern"] == "/health"


def test_find_definition_should_keep_real_express_handler_definition():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "api.js").write_text(
            "app.get('/health', healthCheck)\n"
            "function healthCheck(req, res) { return res; }\n",
        )

        defs = find_definition(root, "healthCheck")

    assert defs
    assert defs[0]["kind"] == "function"
    assert defs[0]["file"] == "api.js"


def test_find_callers_should_keep_real_typescript_service_usage():
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


def test_find_callers_should_not_use_catch_parameter_as_fake_caller():
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


# ---------------------------------------------------------------------------
# find_definition — no private sort keys in results
# ---------------------------------------------------------------------------

def test_find_definition_results_contain_no_private_keys(tmp_path):
    """find_definition must not leak internal sort keys (_exact_match, _definition_priority)."""
    src = """\
def process_data(items):
    return list(items)
"""
    (tmp_path / "data.py").write_text(src)
    results = find_definition(tmp_path, "process_data")
    assert results, "find_definition must return at least one result"
    for result in results:
        private_keys = [k for k in result if k.startswith("_")]
        assert not private_keys, \
            f"Private sort keys must not appear in find_definition results: {private_keys}"
        assert set(result.keys()) <= {"file", "line", "kind"}, \
            f"Unexpected keys in result: {set(result.keys())}"
