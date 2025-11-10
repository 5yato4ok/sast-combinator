from __future__ import annotations

import responses

from pipeline.defect_dojo.client import DojoConfig
from pipeline.defect_dojo.sast_client import SastPipelineDDClient


class RepoParams:
    # Minimal object used by SastPipelineDDClient.upload_report
    def __init__(self, repo_url=None, branch_tag=None, commit_hash=None):
        self.repo_url = repo_url
        self.branch_tag = branch_tag
        self.commit_hash = commit_hash


@responses.activate
def test_upload_report_trim_and_enrich_flow(tmp_path, dojo_base_url, dojo_token):
    cfg = DojoConfig(url=dojo_base_url, verify_ssl=False)
    client = SastPipelineDDClient(cfg, dojo_token)

    # Fake product find/create
    responses.add(responses.GET, f"{dojo_base_url}/api/v2/products/",
                  json={"results": [], "next": None}, status=200)
    responses.add(responses.POST, f"{dojo_base_url}/api/v2/products/",
                  json={"id": 1, "name": "Prod"}, status=201)

    # Ensure engagement -> create
    responses.add(responses.GET, f"{dojo_base_url}/api/v2/engagements/",
                  json={"results": [], "next": None}, status=200)
    responses.add(responses.POST, f"{dojo_base_url}/api/v2/engagements/",
                  json={"id": 22, "name": "an:abc123", "product": 1}, status=201)

    # Import scan returning 'test' id
    responses.add(responses.POST, f"{dojo_base_url}/api/v2/import-scan/",
                  json={"test": 100}, status=200)

    # Findings for that test: two items
    responses.add(
        responses.GET, f"{dojo_base_url}/api/v2/findings/",
        match=[responses.matchers.query_param_matcher({"test":"100","limit":"200","offset":"0"})],
        json={"results": [
            {"id": 501, "file_path": "/home/ci/build/src/utils/a.py", "test": {"id": 100}},
            {"id": 502, "file_path": "/home/ci/build/src/build/utils/b.py", "test": {"id": 100}},
        ], "next": None}, status=200
    )

    responses.add(responses.PATCH, f"{dojo_base_url}/api/v2/findings/501/",
                  json={"id": 501, "file_path": "utils/a.py"}, status=200)
    responses.add(responses.PATCH, f"{dojo_base_url}/api/v2/findings/502/",
                  json={"id": 502, "file_path": "build/utils/b.py"}, status=200)

    # For enrichment: add metadata; first link 200, second 404 -> should DELETE second finding

    responses.add(responses.GET, "https://git.example/repo/blob/abc123/utils/a.py", status=200)
    responses.add(responses.GET, "https://git.example/repo/blob/build/utils/b.py", status=404)

    responses.add(responses.POST, f"{dojo_base_url}/api/v2/findings/501/metadata/",
                  json={"name":"sourcefile_link","value":"ok"}, status=201)
    responses.add(responses.DELETE, f"{dojo_base_url}/api/v2/findings/502/",
                  status=204)

    # Prepare dummy report file
    fp = tmp_path / "report.sarif"
    fp.write_text("{}")

    result = client.upload_report(
        analyzer_name="an",
        product_name="Prod",
        scan_type="SARIF",
        report_path=str(fp),
        repo_params=RepoParams(repo_url="https://git.example/repo", commit_hash="abc123"),
        trim_path="/home/ci/build/src",
    )
    assert result.imported_findings == 2
    assert result.enriched_count == 1  # second was deleted due to 404


@responses.activate
def test_enrich_existing_pagination_and_only_missing(dojo_base_url, dojo_token):
    cfg = DojoConfig(url=dojo_base_url, verify_ssl=False)
    client = SastPipelineDDClient(cfg, dojo_token)

    # Page 1 with 2 findings -> one already has meta, one not
    responses.add(
        responses.GET, f"{dojo_base_url}/api/v2/findings/",
        match=[responses.matchers.query_string_matcher("related_fields=true&limit=200&offset=0")],
        json={"results": [
            {"id": 1, "file_path": "a.py", "test": {"engagement": {"id": 10, "source_code_management_uri":"https://git/repo","commit_hash":"abc"}}},
            {"id": 2, "file_path": "b.py", "test": {"engagement": {"id": 10, "source_code_management_uri":"https://git/repo","commit_hash":"abc"}}},
        ], "next": f"{dojo_base_url}/api/v2/findings/?offset=200" }, status=200
    )
    responses.add(
        responses.GET, f"{dojo_base_url}/api/v2/findings/",
        match=[responses.matchers.query_string_matcher("related_fields=true&limit=200&offset=200")],
        json={"results": [], "next": None}, status=200
    )

    # has_sourcefile_link: id=1 True, id=2 False
    responses.add(
        responses.GET, f"{dojo_base_url}/api/v2/findings/1/metadata/",
        json={"results":[{"name":"sourcefile_link","value":"x"}]}, status=200
    )
    responses.add(
        responses.GET, f"{dojo_base_url}/api/v2/findings/2/metadata/",
        json={"results":[]}, status=200
    )
    responses.add(
        responses.POST, f"{dojo_base_url}/api/v2/findings/2/metadata/",
        json={"name":"sourcefile_link","value":"ok"}, status=201
    )

    # External link -> 200 so metadata is added
    responses.add(responses.GET, "https://git/repo/blob/abc/b.py", status=200)

    updated = client.enrich_existing(product_name=None, only_missing=True, max_workers=4)
    assert updated == 1
