from __future__ import annotations

import responses

from pipeline.defect_dojo.client import DojoConfig, DefectDojoClient


@responses.activate
def test_retry_get_products_429_then_200(dojo_base_url, dojo_token):
    cfg = DojoConfig(url=dojo_base_url, verify_ssl=False)
    client = DefectDojoClient(cfg, dojo_token)

    # First call -> 429, second -> 200
    responses.add(responses.GET, f"{dojo_base_url}/api/v2/products/",
                  status=429, json={"detail": "Too Many Requests"})
    responses.add(responses.GET, f"{dojo_base_url}/api/v2/products/",
                  status=200, json={"results":[{"id":1,"name":"Prod"}], "next": None})

    p = client.get_product_by_name("Prod")
    assert p and p["id"] == 1
    # Ensure both responses were consumed
    assert len(responses.calls) == 2


@responses.activate
def test_retry_findings_500_then_200(dojo_base_url, dojo_token):
    cfg = DojoConfig(url=dojo_base_url, verify_ssl=False)
    client = DefectDojoClient(cfg, dojo_token)

    # First page -> 500, then -> 200; client.iter_findings should succeed
    responses.add(responses.GET, f"{dojo_base_url}/api/v2/findings/",
                  status=500, json={"detail": "Server error"})
    responses.add(responses.GET, f"{dojo_base_url}/api/v2/findings/",
                  status=200, json={"results":[{"id":1},{"id":2}], "next": None})

    items = list(client.iter_findings(limit=200))
    assert [i["id"] for i in items] == [1, 2]
    assert len(responses.calls) == 2
