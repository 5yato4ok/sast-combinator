from __future__ import annotations

import responses

from pipeline.defect_dojo.client import DojoConfig
from pipeline.defect_dojo.sast_client import SastPipelineDDClient


class RepoParams:
    def __init__(self, repo_url=None, branch_tag=None, commit_hash=None):
        self.repo_url = repo_url
        self.branch_tag = branch_tag
        self.commit_hash = commit_hash


def _common_setup(dojo_base_url):
    # Products: not found -> create
    responses.add(responses.GET, f"{dojo_base_url}/api/v2/products/",
                  json={"results": [], "next": None}, status=200)
    responses.add(responses.POST, f"{dojo_base_url}/api/v2/products/",
                  json={"id": 1, "name": "Prod"}, status=201)
    # Engagements: none -> create
    responses.add(responses.GET, f"{dojo_base_url}/api/v2/engagements/",
                  json={"results": [], "next": None}, status=200)
    responses.add(responses.POST, f"{dojo_base_url}/api/v2/engagements/",
                  json={"id": 22, "name": "an-abc", "product": 1}, status=201)


@responses.activate
def test_import_scan_returns_test_dict(tmp_path, dojo_base_url, dojo_token):
    cfg = DojoConfig(url=dojo_base_url, verify_ssl=False)
    client = SastPipelineDDClient(cfg, dojo_token)
    _common_setup(dojo_base_url)

    responses.add(responses.POST, f"{dojo_base_url}/api/v2/import-scan/",
                  json={"test": {"id": 41}}, status=200)

    # Fetch findings for test 41
    responses.add(responses.GET, f"{dojo_base_url}/api/v2/findings/",
                  match=[responses.matchers.query_param_matcher({"test":"41","limit":"200","offset":"0"})],
                  json={"results":[{"id":1,"file_path":"src/a.py","test":{"id":41}}], "next": None}, status=200)

    # No trim/enrich to keep it simple
    rpt = tmp_path / "r.sarif"; rpt.write_text("{}")
    res = client.upload_report("an","Prod","SARIF",str(rpt), RepoParams(), trim_path="")
    assert res.test_id == 41
    assert res.imported_findings == 1


@responses.activate
def test_import_scan_returns_test_int(tmp_path, dojo_base_url, dojo_token):
    cfg = DojoConfig(url=dojo_base_url, verify_ssl=False)
    client = SastPipelineDDClient(cfg, dojo_token)
    _common_setup(dojo_base_url)

    responses.add(responses.POST, f"{dojo_base_url}/api/v2/import-scan/",
                  json={"test": 42}, status=200)
    responses.add(responses.GET, f"{dojo_base_url}/api/v2/findings/",
                  match=[responses.matchers.query_param_matcher({"test":"42","limit":"200","offset":"0"})],
                  json={"results":[{"id":2,"file_path":"src/b.py","test":{"id":42}}], "next": None}, status=200)

    rpt = tmp_path / "r.sarif"; rpt.write_text("{}")
    res = client.upload_report("an","Prod","SARIF",str(rpt), RepoParams(), trim_path="")
    assert res.test_id == 42
    assert res.imported_findings == 1


@responses.activate
def test_import_scan_returns_findings_list(tmp_path, dojo_base_url, dojo_token):
    cfg = DojoConfig(url=dojo_base_url, verify_ssl=False)
    client = SastPipelineDDClient(cfg, dojo_token)
    _common_setup(dojo_base_url)

    # Return list of finding IDs from import-scan
    responses.add(responses.POST, f"{dojo_base_url}/api/v2/import-scan/",
                  json={"findings": [101, 102]}, status=200)
    # Client should GET each finding by id
    responses.add(responses.GET, f"{dojo_base_url}/api/v2/findings/101/",
                  json={"id":101,"file_path":"src/x.py","test":{"id":77}}, status=200)
    responses.add(responses.GET, f"{dojo_base_url}/api/v2/findings/102/",
                  json={"id":102,"file_path":"src/y.py","test":{"id":77}}, status=200)

    rpt = tmp_path / "r.sarif"; rpt.write_text("{}")
    res = client.upload_report("an","Prod","SARIF",str(rpt), RepoParams(), trim_path="")
    assert res.imported_findings == 2
