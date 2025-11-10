# Common pytest fixtures for defect_dojo tests.
# We ensure the project root (directory that contains the `pipeline/` package) is in sys.path.

import os
import sys
import pytest

PROJECT_ROOT = os.getenv("PROJECT_ROOT") or os.getcwd()
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

@pytest.fixture()
def dojo_base_url():
    return "https://dojo.test"

@pytest.fixture()
def dojo_token(monkeypatch):
    # Ensure code paths that read DEFECTDOJO_TOKEN do not fail
    monkeypatch.setenv("DEFECTDOJO_TOKEN", "test-token")
    return "test-token"
