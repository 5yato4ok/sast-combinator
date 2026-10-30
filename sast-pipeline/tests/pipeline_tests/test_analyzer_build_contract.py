"""``AnalyzerBuild`` is the wire shape AIST stores verbatim under ``analyzer_versions``.

AIST does not interpret analyzer data, so the shape has to be correct where it is produced.
"""

import pytest

from pipeline.contracts import AnalyzerBuild


def test_a_fully_identified_build_carries_every_field():
    build = AnalyzerBuild(
        analyzer="semgrep",
        image="sast-semgrep",
        image_id="sha256:feedface",
        tool_version="semgrep 1.183.0",
    )

    assert build.is_identified
    assert build.to_wire() == {
        "analyzer": "semgrep",
        "image": "sast-semgrep",
        "image_id": "sha256:feedface",
        "tool_version": "semgrep 1.183.0",
    }


def test_a_field_the_image_could_not_answer_for_is_omitted_not_blanked():
    """A blank would read as a known-empty version; absent reads as unknown, which is the truth."""
    build = AnalyzerBuild(analyzer="snyk", image="sast-snyk")

    assert build.to_wire() == {"analyzer": "snyk", "image": "sast-snyk"}


def test_a_build_with_nothing_identifying_is_not_a_version():
    assert not AnalyzerBuild(analyzer="legacy", image="").is_identified
    assert AnalyzerBuild(analyzer="legacy", image="", tool_version="bearer v2.1.3").is_identified


@pytest.mark.parametrize("name", ["", "   "])
def test_a_build_must_name_its_analyzer(name):
    with pytest.raises(ValueError):
        AnalyzerBuild(analyzer=name, image="sast-semgrep")


def test_the_record_is_immutable_once_built():
    build = AnalyzerBuild(analyzer="bearer", image="bearer-analyzer")
    with pytest.raises(Exception):
        build.analyzer = "semgrep"
