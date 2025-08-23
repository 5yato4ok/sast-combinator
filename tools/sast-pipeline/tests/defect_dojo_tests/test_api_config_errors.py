from __future__ import annotations

import os
import pytest
import yaml

from pipeline.defect_dojo.utils import load_dojo_config


def test_load_dojo_config_requires_url(tmp_path, monkeypatch):
    # Create minimal YAML without URL
    cfg_path = tmp_path / "dojo.yaml"
    cfg_path.write_text(yaml.safe_dump({"defectdojo": {"verify_ssl": False}}))

    with pytest.raises(ValueError):
        load_dojo_config(str(cfg_path))
