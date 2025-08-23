from __future__ import annotations

import responses

from pipeline.defect_dojo.client import DojoConfig, DefectDojoClient


@responses.activate
def test_ensure_engagement_create_and_patch(dojo_base_url, dojo_token):
    cfg = DojoConfig(url=dojo_base_url, verify_ssl=False)

    # 1) No engagements -> create
    responses.add(
        responses.GET, f"{dojo_base_url}/api/v2/engagements/",
        json={"results": [], "next": None}, status=200
    )
    created = {
        "id": 11, "product": 1, "name": "Analyzer-abc123",
        "source_code_management_uri": "https://git/repo",
        "branch_tag": "main", "commit_hash": "abc12345"
    }
    responses.add(
        responses.POST, f"{dojo_base_url}/api/v2/engagements/",
        json=created, status=201
    )

    client = DefectDojoClient(cfg, dojo_token)
    eng = client.ensure_engagement(
        product_id=1, name="Analyzer-abc123",
        repo_url="https://git/repo", branch_tag="main", commit_hash="abc12345",
        engagement_status="In Progress"
    )
    assert eng["id"] == 11

    # 2) Engagement exists but fields differ -> PATCH
    responses.reset()
    responses.add(
        responses.GET, f"{dojo_base_url}/api/v2/engagements/",
        json={"results": [dict(created, source_code_management_uri="https://git/old")], "next": None}, status=200
    )
    patched = dict(created, source_code_management_uri="https://git/repo")
    responses.add(
        responses.PATCH, f"{dojo_base_url}/api/v2/engagements/11/",
        json=patched, status=200
    )
    eng2 = client.ensure_engagement(
        product_id=1, name="Analyzer-abc123",
        repo_url="https://git/repo", branch_tag="main", commit_hash="abc12345",
        engagement_status="In Progress"
    )
    assert eng2["source_code_management_uri"] == "https://git/repo"


@responses.activate
def test_get_or_create_product(dojo_base_url, dojo_token):
    cfg = DojoConfig(url=dojo_base_url, verify_ssl=False)

    # No product -> create
    responses.add(
        responses.GET, f"{dojo_base_url}/api/v2/products/",
        json={"results": [], "next": None}, status=200
    )
    responses.add(
        responses.POST, f"{dojo_base_url}/api/v2/products/",
        json={"id": 7, "name": "MyProduct"}, status=201
    )
    client = DefectDojoClient(cfg, dojo_token)
    p = client.get_or_create_product("MyProduct")
    assert p["id"] == 7

    # Found by name -> returns first
    responses.reset()
    responses.add(
        responses.GET, f"{dojo_base_url}/api/v2/products/",
        json={"results": [{"id":9,"name":"MyProduct"}], "next": None}, status=200
    )
    p = client.get_or_create_product("MyProduct")
    assert p["id"] == 9
