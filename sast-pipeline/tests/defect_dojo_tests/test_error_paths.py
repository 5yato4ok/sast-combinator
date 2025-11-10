from __future__ import annotations

import responses

from pipeline.defect_dojo.client import DojoConfig
from pipeline.defect_dojo.sast_client import SastPipelineDDClient


class RepoParams:
    def __init__(self, repo_url=None, branch_tag=None, commit_hash=None):
        self.repo_url = repo_url
        self.branch_tag = branch_tag
        self.commit_hash = commit_hash


@responses.activate
def test_enrich_handles_metadata_500_gracefully(tmp_path, dojo_base_url, dojo_token):
    cfg = DojoConfig(url=dojo_base_url, verify_ssl=False)
    client = SastPipelineDDClient(cfg, dojo_token)

    # Arrange: product/engagement/import/test findings
    responses.add(responses.GET, f"{dojo_base_url}/api/v2/products/",
                  json={"results": [], "next": None}, status=200)
    responses.add(responses.POST, f"{dojo_base_url}/api/v2/products/",
                  json={"id": 1, "name": "Prod"}, status=201)
    responses.add(responses.GET, f"{dojo_base_url}/api/v2/engagements/",
                  json={"results": [], "next": None}, status=200)
    responses.add(responses.POST, f"{dojo_base_url}/api/v2/engagements/",
                  json={"id": 9, "name": "an-abc", "product": 1}, status=201)
    responses.add(responses.POST, f"{dojo_base_url}/api/v2/import-scan/",
                  json={"test": 5}, status=200)
    responses.add(responses.GET, f"{dojo_base_url}/api/v2/findings/",
                  json={"results":[{"id":1,"file_path":"a.py","test":{"id":5}}], "next": None}, status=200)

    # Link check 200, but metadata POST fails with 500 -> method should not raise, just count 0
    responses.add(responses.GET, "https://git/repo/blob/abc/a.py", status=200)
    responses.add(responses.POST, f"{dojo_base_url}/api/v2/findings/1/metadata/",
                  status=500, json={"detail":"boom"})

    fp = tmp_path / "r.sarif"; fp.write_text("{}")
    res = client.upload_report(
        analyzer_name="an",
        product_name="Prod",
        scan_type="SARIF",
        report_path=str(fp),
        repo_params=RepoParams(repo_url="https://git/repo", commit_hash="abc"),
        trim_path="",
    )
    assert res.enriched_count == 0
