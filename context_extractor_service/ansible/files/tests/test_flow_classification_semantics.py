import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.config_analysis import classify_environment
from context_extractor.project_analysis import classify_file


def test_classify_file_should_keep_real_runtime_and_vendor_shapes():
    assert classify_file("src/app/debug/oauth/page.tsx")["type"] == "production"
    assert classify_file("front_end/common/scripts/vendor/firebase-app.js")["type"] == "vendored"
    assert classify_file("front_end/libs/services/nx-cloud-api/cloud-services/channel-partners/channel-partners-api.spec.ts")[
        "type"
    ] == "test"


def test_classify_file_should_route_github_workflow_into_config_flow():
    result = classify_file(".github/workflows/ci.yml")

    assert result["type"] == "config"


def test_classify_file_should_route_build_script_into_config_flow():
    result = classify_file("build_scripts/preprocess.py")

    assert result["type"] == "config"


def test_classify_file_should_keep_source_modules_out_of_content_based_config_fallback():
    result = classify_file(
        "src/runtime/config.ts",
        "export const token = process.env.API_TOKEN;\nexport const password = 'x';\n",
    )

    assert result["type"] == "production"


def test_classify_file_should_prefer_vendored_path_signal_over_minified_asset_rule():
    result = classify_file("vendor/assets/jquery.min.js")

    assert result["type"] == "vendored"


def test_classify_environment_should_keep_real_prod_dev_template_shapes():
    assert classify_environment("deploy/docker-compose.prod.yml")["environment"] == "production"
    assert classify_environment("deploy/docker-compose.override.yml")["environment"] == "dev"
    assert classify_environment(".env.example")["environment"] == "template"
