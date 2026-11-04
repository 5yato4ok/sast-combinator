from pipeline.config_utils import AnalyzerReport


def test_a_sarif_analyzer_without_an_explicit_result_file_is_read_from_its_named_sarif_file():
    report = AnalyzerReport.of({"name": "semgrep"})

    assert (report.analyzer_name, report.result_file, report.scan_type) == ("semgrep", "semgrep_result.sarif", "SARIF")


def test_an_xml_analyzer_is_imported_as_generic_xml_from_a_json_named_file():
    report = AnalyzerReport.of({"name": "horusec", "output_type": "generic-xml"})

    assert (report.result_file, report.scan_type) == ("horusec_result.json", "Generic XML Import")


def test_an_explicit_result_file_and_scan_type_are_kept():
    report = AnalyzerReport.of({"name": "claude-diff-security", "output_type": "Claude Diff Security",
                                "result_file": "claude-diff-security_result.json"})

    assert (report.result_file, report.scan_type) == ("claude-diff-security_result.json", "Claude Diff Security")
