"""Tests for the ``pipeline.config_utils`` module.

These tests cover the behaviour of the ``AnalyzersConfigHelper`` class
including its ability to expand language‑specific analyzer
configurations, compute derived values, filter analyzers for a
pipeline run and pretty print summary tables.  Error conditions such
as undefined inheritance targets and cyclic inheritance are also
validated.

The tests operate on synthetic analyzer definitions rather than
reading from disk wherever possible.  Temporary files are used only
for APIs that explicitly write to the filesystem.
"""

import os
import io
import json
import yaml
from pathlib import Path
from pipeline.config_utils import AnalyzersConfigHelper as AH

import pytest


def test_get_analyzer_result_file_name_defaults():
    """Verify that result file names are constructed based on the analyzer
    name and output type when an explicit ``result_file`` is not
    provided."""
    # Default SARIF produces ``_result.sarif``
    assert AH.get_analyzer_result_file_name({"name": "abc", "output_type": "sarif"}) == "abc_result.sarif"
    # Non‑SARIF output defaults to json
    assert AH.get_analyzer_result_file_name({"name": "xyz", "output_type": "json"}) == "xyz_result.json"
    # Provided result_file overrides output_type
    assert AH.get_analyzer_result_file_name({"name": "x", "result_file": "custom.out", "output_type": "sarif"}) == "custom.out"


def test_analyzer_time_class_order():
    """The helper exposes the mapping used to order analyzers by time class
    via the ``get_analyzers_time_class`` method."""
    helper = AH.__new__(AH)  # Bypass __init__
    classes = list(helper.get_analyzers_time_class())
    assert classes == ["fast", "medium", "slow"]


def test_expand_analyzers_no_language_specific():
    """If an analyzer does not define language‑specific containers the
    expand routine should simply return a deep copy of the original
    definition."""
    src = [
        {
            "name": "simple",
            "language": "py",
            "image": "img",
        }
    ]
    expanded = AH.expand_analyzers(src)
    assert len(expanded) == 1
    # Changes to the expanded result should not affect the source
    expanded[0]["image"] = "changed"
    assert src[0]["image"] == "img"


def test_expand_analyzers_language_specific(monkeypatch):
    """Multiple language variants should be generated for analyzers with
    language specific containers.  Languages are grouped by their
    inheritance roots."""
    parent = {
        "name": "an",
        "language_specific_containers": True,
        "image": "img",
        # Define multiple language configs, including one that inherits another
        "configuration": [
            {"py": {}},
            {"js": {}},
            {"ts": {"inherits": "js"}},
        ],
    }
    out = AH.expand_analyzers([parent])
    names = {c["name"] for c in out}
    assert names == {"an_py", "an_js"}
    for c in out:
        if c["name"] == "an_py":
            assert c["language"] == ["py"]
            assert c["parent"] == "an"
        elif c["name"] == "an_js":
            # Languages should be sorted and include all languages in the js group
            assert set(c["language"]) == {"js", "ts"}


def test_expand_analyzers_allowed_langs():
    """When an ``allowed_langs`` set is provided, only variants that
    intersect with the allowed languages should be emitted."""
    parent = {
        "name": "an",
        "language_specific_containers": True,
        "image": "img",
        "configuration": [
            {"py": {}},
            {"js": {}},
            {"ts": {"inherits": "js"}},
        ],
    }
    out = AH.expand_analyzers([parent], allowed_langs={"py"})
    assert len(out) == 1
    assert out[0]["name"] == "an_py"
    assert out[0]["language"] == ["py"]


def test_expand_analyzers_missing_inherits_base():
    """Referring to a base language that isn't defined should raise a
    ``ValueError``."""
    bad = {
        "name": "an",
        "language_specific_containers": True,
        "image": "img",
        "configuration": [
            {"ts": {"inherits": "js"}},
        ],
    }
    with pytest.raises(ValueError):
        AH.expand_analyzers([bad])


def test_expand_analyzers_inherits_cycle():
    """A cycle in the inheritance graph should be detected and raise
    ``ValueError``."""
    cyclic = {
        "name": "an",
        "language_specific_containers": True,
        "image": "img",
        "configuration": [
            {"a": {"inherits": "b"}},
            {"b": {"inherits": "a"}},
        ],
    }
    with pytest.raises(ValueError):
        AH.expand_analyzers([cyclic])


def test_expand_analyzers_inherits_extra_keys():
    """Extra keys besides ``inherits``/``inherits_from`` in a language
    configuration should trigger a validation error."""
    bad = {
        "name": "an",
        "language_specific_containers": True,
        "image": "img",
        "configuration": [
            {"py": {"inherits": "js", "unexpected": 1}},
            {"js": {}},
        ],
    }
    with pytest.raises(ValueError):
        AH.expand_analyzers([bad])


def test_get_supported_analyzers(tmp_path):
    """The helper should return a unique list of enabled analyzer names from
    the raw configuration."""
    config = {
        "analyzers": [
            {"name": "a", "enabled": True, "image": "img"},
            {"name": "b", "enabled": False, "image": "img"},
            {"name": "c", "enabled": True, "image": "img"},
            {"name": "a", "enabled": True, "image": "img"},
        ]
    }
    cfg_path = tmp_path / "analyzers.yaml"
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.dump(config, fh)
    helper = AH(str(cfg_path))
    # Order does not matter, but duplicates must be removed and disabled
    # analyzers omitted
    names = set(helper.get_supported_analyzers())
    assert names == {"a", "c"}


def test_get_all_images(tmp_path):
    """``get_all_images`` should return a set of all unique image
    identifiers across analyzer variants."""
    config = {
        "analyzers": [
            {"name": "a", "enabled": True, "image": "i1"},
            {"name": "b", "enabled": True, "image": "i2"},
            {"name": "c", "enabled": True, "image": "i1"},
        ]
    }
    cfg_path = tmp_path / "cfg.yaml"
    with cfg_path.open("w") as fh:
        yaml.dump(config, fh)
    helper = AH(str(cfg_path))
    assert helper.get_all_images() == {"i1", "i2"}


def test_get_supported_languages_caches(tmp_path):
    """The helper should compute and cache the set of languages defined
    across analyzer variants on first call and return the cached
    value on subsequent calls."""
    config = {
        "analyzers": [
            {"name": "x", "image": "img", "language": "py"},
            {"name": "y", "image": "img", "language": ["js", "ts"]},
        ]
    }
    cfg_path = tmp_path / "cfg.yaml"
    with cfg_path.open("w") as fh:
        yaml.dump(config, fh)
    helper = AH(str(cfg_path))
    langs1 = set(helper.get_supported_languages())
    assert langs1 == {"py", "js", "ts"}
    # Modify internal analyzers list after computing languages to ensure
    # the cached value is returned; languages property should not be
    # recomputed automatically.
    helper.analyzers.append({"name": "z", "image": "img", "language": "go"})
    langs2 = set(helper.get_supported_languages())
    assert langs2 == {"py", "js", "ts"}


def test_get_level_values():
    """The helper returns ordinal values for known time classes and a
    fallback for unknown classes."""
    assert AH.get_level("fast") == 0
    assert AH.get_level("medium") == 1
    assert AH.get_level("slow") == 2
    # Unknown classes default to 100
    assert AH.get_level("unknown") == 100


def test_filter_language_specific_config():
    """The internal helper should filter out configuration entries that
    are not in the allowed language set and drop duplicates."""
    config = [
        {"py": {}},
        {"js": {}},
        {"py": {"extra": True}},
        {"ts": {}},
    ]
    out = AH._filter_language_specific_config(config, {"py", "ts"})
    # Only the first occurrence of each allowed language should be kept
    assert out == [{"py": {}}, {"ts": {}}]


def test_prepare_pipeline_analyzer_config(tmp_path, monkeypatch):
    """Filtering analyzers by languages, time class and target set should
    produce a YAML file with only the permitted analyzers.  The
    filename should include the pipeline ID and the contents should
    reflect any trimming of language specific configurations."""
    # Create a temporary YAML configuration with one analyzer that supports
    # both JS and PY but marks language_specific_containers so that
    # configuration filtering is applied.
    config = {
        "analyzers": [
            {
                "name": "multi",
                "image": "img",
                "language": ["py", "js"],
                "time_class": "medium",
                "language_specific_containers": True,
                "configuration": [
                    {"py": {}},
                    {"js": {}},
                    {"ts": {"inherits": "js"}},
                ],
            },
            {
                "name": "slow_one",
                "image": "img2",
                "language": "py",
                "time_class": "slow",
            },
        ]
    }
    cfg_path = tmp_path / "cfg.yaml"
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.dump(config, fh)
    helper = AH(str(cfg_path))
    # Patch the pipeline ID to a constant for reproducibility
    monkeypatch.setenv("PIPELINE_ID", "abcd1234")
    # Filter to only include Python analyzers and exclude slow ones
    filename = helper.prepare_pipeline_analyzer_config(languages=["py"], max_time_class="medium", target_analyzers=None)
    # The returned file should end with the pipeline ID
    assert "abcd1234" in filename
    # Load the generated YAML and verify contents
    with open(filename, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    analyzers = data.get("analyzers", [])
    # Only one analyzer should remain after filtering: the expanded multi analyzer
    assert len(analyzers) == 1
    ana = analyzers[0]
    assert ana["name"] == "multi_py"
    # Its configuration should be trimmed to the allowed languages
    assert ana.get("configuration") is None


def test_pretty_print_table_and_stats(capsys, tmp_path):
    """The ``pretty_print`` method returns a Markdown table summarising
    analyzer variants and a statistics section.  This test checks for
    the presence of expected substrings."""
    config = {
        "analyzers": [
            {"name": "a", "image": "i", "language": "py", "enabled": True},
            {"name": "b", "image": "j", "language": ["js", "ts"], "enabled": False, "commentary": "disabled analyzer"},
            {"name": "c", "image": "k", "language": "py", "enabled": True, "type": "builder", "commentary": ["builder"]},
        ]
    }
    cfg_path = tmp_path / "cfg.yaml"
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.dump(config, fh)
    helper = AH(str(cfg_path))
    table = helper.pretty_print(max_width=60)
    # Check headers
    assert "| # | Name | Langs | InBuild | Enabled | Comment |" in table.splitlines()[0]
    # There should be one row per variant (variants list is flattened)
    # Actually pretty_print aggregates by analyzer name; we check that all names appear
    assert "a" in table and "b" in table and "c" in table
    # Stats should include totals and per‑language metrics
    assert "Total analyzers" in table
    assert "py" in table and "js" in table