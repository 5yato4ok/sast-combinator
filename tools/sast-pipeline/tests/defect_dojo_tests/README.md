# Tests for `pipeline.defect_dojo`

This folder contains a pytest-based test suite that covers the generic client
and the SAST-specific flow. All network I/O to DefectDojo is mocked via `responses`.

## Layout
- `tests/test_client.py` – Unit tests for `DefectDojoClient`
- `tests/test_sast_client.py` – Scenario tests for `SastPipelineDDClient`
- `tests/test_utils_delete.py` – Test for `delete_findings_by_product_and_path_prefix` (monkeypatched)
- `requirements-dev.txt` – Dev dependencies

## Install & run
From your repo root (directory that contains the `pipeline/` package):

```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r tests/requirements-dev.txt
pytest -q tests/defect_dojo_tests
```

If your project root path is unusual, set it explicitly:
```bash
PROJECT_ROOT=$(pwd) pytest -q defect_dojo_tests/tests
```

## Optional OpenAPI schema tests
If you have a full OpenAPI document for your DefectDojo instance, add a separate Schemathesis test file.
