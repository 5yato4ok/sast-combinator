import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.project_analysis import classify_file, find_callers


def test_find_callers_should_not_treat_catch_parameter_as_caller_name():
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


def test_classify_file_should_route_jenkinsfile_into_config_flow():
    result = classify_file("Jenkinsfile")

    assert result["type"] == "config"


def test_find_callers_should_leave_top_level_catch_without_fake_caller_for_simple_case():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "main.js").write_text(
            "function handleFailure(error) {\n"
            "  console.error(error.message);\n"
            "}\n"
            "\n"
            "async function main() {\n"
            "  return true;\n"
            "}\n"
            "\n"
            "main().catch(handleFailure);\n",
        )

        callers = find_callers(root, "main.js", "main")

    assert callers
    assert callers[0]["caller_function"] is None


def test_classify_file_should_keep_normal_runtime_page_in_code_flow():
    result = classify_file("src/app/debug/oauth/page.tsx")

    assert result["type"] == "production"
