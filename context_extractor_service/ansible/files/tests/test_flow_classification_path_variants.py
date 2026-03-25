import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.project_analysis import classify_file


def test_classify_file_should_keep_known_vendored_and_generated_assets():
    assert classify_file("cloud/cms/static/tinymce/js/tinymce/tinymce.min.js")["type"] in {
        "generated",
        "vendored",
    }
    assert classify_file("help/cms/jquery.js")["type"] == "vendored"


def test_classify_file_should_keep_known_test_and_config_shapes():
    assert classify_file("cloud/cloud/settings.py")["type"] == "config"
    assert classify_file("front_end/libs/services/nx-cloud-api/cloud-services/channel-partners/channel-partners-api.spec.ts")[
        "type"
    ] == "test"
    assert classify_file("cloud/ams/deploy/ams_service_crash_receiver/Dockerfile")["type"] == "config"


def test_classify_file_should_route_jenkinsfile_into_config_flow():
    result = classify_file("Jenkinsfile")

    assert result["type"] == "config"


def test_classify_file_should_route_etc_script_into_config_flow():
    result = classify_file("etc/scripts/copy_nginx_configs.py")

    assert result["type"] == "config"
