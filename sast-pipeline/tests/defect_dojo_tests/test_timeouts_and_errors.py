from __future__ import annotations

import pytest
import responses
import requests

from pipeline.defect_dojo.client import DojoConfig, DefectDojoClient


@responses.activate
def test_timeout_is_propagated(dojo_base_url, dojo_token, monkeypatch):
    cfg = DojoConfig(url=dojo_base_url, verify_ssl=False)
    client = DefectDojoClient(cfg, dojo_token)

    # Simulate requests timeout via responses callback raising requests.Timeout
    def _raise_timeout(request):
        raise requests.Timeout("simulated timeout")

    responses.add_callback(
        responses.GET, f"{dojo_base_url}/api/v2/findings/",
        callback=lambda req: _raise_timeout(req)
    )

    with pytest.raises(requests.Timeout):
        # Any method that triggers GET /findings should propagate the timeout
        list(client.iter_findings(limit=200))


@responses.activate
def test_delete_handles_http_error_gracefully(dojo_base_url, dojo_token):
    cfg = DojoConfig(url=dojo_base_url, verify_ssl=False)
    client = DefectDojoClient(cfg, dojo_token)

    # DELETE returns 500 -> raises for status
    responses.add(responses.DELETE, f"{dojo_base_url}/api/v2/findings/999/",
                  status=500, json={"detail":"boom"})
    with pytest.raises(requests.HTTPError):
        client.delete_finding(999)
