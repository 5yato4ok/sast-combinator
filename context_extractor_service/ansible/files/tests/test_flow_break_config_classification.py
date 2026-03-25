import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.project_analysis import classify_file


def test_classify_file_should_route_github_workflow_into_config_flow():
    result = classify_file(".github/workflows/ci.yml")

    assert result["type"] == "config"


def test_classify_file_should_route_build_script_into_config_flow():
    result = classify_file("build_scripts/preprocess.py")

    assert result["type"] == "config"


def test_classify_file_should_keep_normal_runtime_script_in_code_flow():
    result = classify_file("cloud/cms/static/js/menuChange.js")

    assert result["type"] == "production"
