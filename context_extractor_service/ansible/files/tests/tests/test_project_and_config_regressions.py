import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context_extractor.config_analysis import find_related_configs
from context_extractor.project_analysis import classify_file


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "related_config_regression"


def test_classify_file_should_treat_minified_third_party_asset_as_non_production():
    result = classify_file("cloud/cms/static/tinymce/js/tinymce/tinymce.min.js")

    assert result["type"] in {"vendored", "generated"}


def test_classify_file_should_treat_bundled_jquery_asset_as_non_production():
    result = classify_file("help/cms/jquery.js")

    assert result["type"] in {"vendored", "generated"}


def test_find_related_configs_should_ignore_plain_text_mentions_of_origin_filename():
    result = find_related_configs(FIXTURES, "Dockerfile")

    assert result == []
