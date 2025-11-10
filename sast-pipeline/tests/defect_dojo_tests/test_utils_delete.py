from __future__ import annotations

import pytest

from pipeline.defect_dojo import utils as dd_utils


class DummyClient:
    def __init__(self):
        self.deleted = []

    def iter_findings(self, product_name: str, limit: int):
        # Simulate three findings, two match prefix 'utils/'
        yield {"id": 1, "file_path": "utils/a.py"}
        yield {"id": 2, "file_path": "core/b.py"}
        yield {"id": 3, "file_path": "utils/c.py"}

    def delete_finding(self, fid: int) -> None:
        self.deleted.append(fid)


def test_delete_findings_by_product_and_path_prefix_monkeypatch(monkeypatch, tmp_path):
    # Patch utils to use our DummyClient instead of real SastPipelineDDClient
    monkeypatch.setenv("DEFECTDOJO_TOKEN", "x")
    monkeypatch.setattr(dd_utils, "load_dojo_config", lambda *_: object())
    monkeypatch.setattr(dd_utils, "SastPipelineDDClient", lambda *_: DummyClient())

    matched, deleted = dd_utils.delete_findings_by_product_and_path_prefix(
        product_name="Prod",
        path_prefix="utils",
        dojo_cfg_path=str(tmp_path / "defectdojo.yaml"),
        dry_run=False,
    )
    assert matched == 2 and deleted == 2
