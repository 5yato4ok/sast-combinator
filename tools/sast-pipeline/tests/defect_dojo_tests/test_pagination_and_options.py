from __future__ import annotations

import responses

from pipeline.defect_dojo.client import DojoConfig, DefectDojoClient
from pipeline.defect_dojo.sast_client import SastPipelineDDClient


@responses.activate
def test_iter_findings_two_pages(dojo_base_url, dojo_token):
    cfg = DojoConfig(url=dojo_base_url, verify_ssl=False)
    client = DefectDojoClient(cfg, dojo_token)

    # Page 1
    responses.add(
        responses.GET, f"{dojo_base_url}/api/v2/findings/",
        json={"results":[{"id":1},{"id":2}], "next": f"{dojo_base_url}/api/v2/findings/?offset=200"},
        status=200
    )
    # Page 2
    responses.add(
        responses.GET, f"{dojo_base_url}/api/v2/findings/",
        json={"results":[{"id":3}], "next": None},
        status=200
    )

    ids = [f["id"] for f in client.iter_findings(limit=200)]
    assert ids == [1,2,3]


@responses.activate
def test_enrich_only_missing_false_overwrites_meta(dojo_base_url, dojo_token):
    cfg = DojoConfig(url=dojo_base_url, verify_ssl=False)
    client = SastPipelineDDClient(cfg, dojo_token)

    # Single page with one finding
    responses.add(
        responses.GET, f"{dojo_base_url}/api/v2/findings/",
        json={"results":[{"id":1,"file_path":"a.py","test":{"engagement":{"id":5,"source_code_management_uri":"https://git/repo","branch_tag":"main"}}}], "next": None},
        status=200
    )
    # has_sourcefile_link -> True (would be skipped only if only_missing=True)
    responses.add(
        responses.GET, f"{dojo_base_url}/api/v2/findings/1/metadata/",
        json={"results":[{"name":"sourcefile_link","value":"old"}]}, status=200
    )
    # External link is valid
    responses.add(responses.GET, "https://git/repo/blob/main/a.py", status=200)
    # Post new metadata (should be called because only_missing=False)
    responses.add(responses.POST, f"{dojo_base_url}/api/v2/findings/1/metadata/",
                  json={"name":"sourcefile_link","value":"new"}, status=201)

    updated = client.enrich_existing(product_name=None, only_missing=False, max_workers=2)
    assert updated == 1
