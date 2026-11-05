from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pipeline.defect_dojo import utils as dd_utils


class RecordingClient:
    def __init__(self):
        self.uploaded: list[tuple[str, str, str]] = []

    def upload_report(self, analyzer_name, product_name, scan_type, report_path, repo_params, trim_path):
        self.uploaded.append((analyzer_name, scan_type, Path(report_path).name))
        return analyzer_name


def _upload(monkeypatch, tmp_path: Path, client: RecordingClient | None = None):
    monkeypatch.setattr(dd_utils, "load_dojo_config", lambda *_: object())
    monkeypatch.setattr(dd_utils, "SastPipelineDDClient", lambda *_: client)
    monkeypatch.setattr(dd_utils, "read_repo_params", lambda *_: None)
    config_path = tmp_path / "analyzers.yaml"
    config_path.write_text(yaml.safe_dump({"analyzers": [
        {"name": "eslint_security", "type": "simple", "output_type": "SARIF"},
        {"name": "semgrep", "type": "simple", "output_type": "Semgrep JSON Report"},
    ]}), encoding="utf-8")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "eslint_security_result.sarif").write_text("", encoding="utf-8")
    (output_dir / "semgrep_result.json").write_text('{"results": []}', encoding="utf-8")
    return dd_utils.upload_results(
        output_dir=str(output_dir),
        analyzers_cfg_path=str(config_path),
        product_name="Prod",
        dojo_config_path=str(tmp_path / "defectdojo.yaml"),
        repo_path=str(tmp_path),
        trim_path="",
    )


def test_upload_sends_only_the_reports_the_analyzers_produced(monkeypatch, tmp_path):
    monkeypatch.setenv("DEFECTDOJO_TOKEN", "test-token")
    client = RecordingClient()

    results = _upload(monkeypatch, tmp_path, client)

    assert client.uploaded == [("semgrep", "Semgrep JSON Report", "semgrep_result.json")]
    assert results == ["semgrep"]


def test_upload_without_a_token_is_refused(monkeypatch, tmp_path):
    monkeypatch.delenv("DEFECTDOJO_TOKEN", raising=False)

    with pytest.raises(ValueError, match="DEFECTDOJO_TOKEN"):
        _upload(monkeypatch, tmp_path, RecordingClient())
