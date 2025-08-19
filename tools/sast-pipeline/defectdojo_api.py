#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
defectdojo_api.py

Single-file helper to:
- load DefectDojo config (YAML + environment overrides)
- resolve scan_type (from analyzers.yaml or auto by file extension)
- upload a report to DefectDojo (auto-create product/engagement)
- create metadata "sourcefile_link" for all findings produced by the import

NOTES
- Engagement naming: defaults to "<analyzer>-<short_sha>" if local Git info is available,
  otherwise falls back to "<analyzer>". You can change NAME_MODE below.
- New engagement per commit is recommended for immutable source links. As an alternative,
  you could keep one engagement per branch and store the commit in Test.build_id.

Environment variables
- DEFECTDOJO_TOKEN (required): API token

"""

from __future__ import annotations

import os
import re
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Tuple
from repo_info import read_repo_params

import requests

try:
    import yaml  # type: ignore
except Exception as e:
    yaml = None

# ------------------------------ configuration ------------------------------

@dataclass
class DojoConfig:
    url: str
    verify_ssl: bool = True
    minimum_severity: str = "Info"

    @staticmethod
    def _parse_bool(v: Optional[str], default: bool) -> bool:
        if v is None:
            return default
        return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}

def load_dojo_config(config_path: str) -> DojoConfig:
    """Load YAML config and apply environment overrides."""
    if yaml is None:
        raise RuntimeError("PyYAML is required. Install 'pyyaml'.")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    dd = data.get("defectdojo", {}) or {}
    url = os.environ.get("DEFECTDOJO_URL") or dd.get("url") or ""
    if not url:
        raise ValueError("Missing DefectDojo URL (defectdojo.url or DEFECTDOJO_URL).")

    verify_ssl = DojoConfig._parse_bool(os.environ.get("DEFECTDOJO_VERIFY_SSL"), bool(dd.get("verify_ssl", True)))
    minimum_severity = os.environ.get("DEFECTDOJO_MIN_SEVERITY") or dd.get("minimum_severity", "Info")
    return DojoConfig(url=url.rstrip("/"), verify_ssl=verify_ssl, minimum_severity=minimum_severity)

# ------------------------------ scan type logic ----------------------------

def resolve_scan_type(analyzers_cfg_path: Optional[str], analyzer_name: Optional[str], report_path: str) -> str:
    """
    Decide scan_type. Priority:
      1) analyzers.yaml mapping: analyzers[<name>].scan_type
      2) file extension heuristic (SARIF preferred)
    """
    # 1) analyzers.yaml mapping
    if analyzers_cfg_path and analyzer_name and os.path.exists(analyzers_cfg_path):
        try:
            with open(analyzers_cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            mapping = (data.get("analyzers") or {}).get(analyzer_name) or {}
            st = mapping.get("output_type")
            if st:
                return st
        except Exception:
            pass

    # 2) extension heuristic
    base, ext = os.path.splitext(report_path.lower())
    if ext in (".sarif", ".sarif.json"):
        return "SARIF"
    if ext == ".xml":
        return "Generic XML Import"
    if ext == ".json":
        # Light SARIF detection
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                head = f.read(4096)
            if '"$schema"' in head and "sarif" in head.lower():
                return "SARIF"
        except Exception:
            pass
        return "Generic Findings Import"
    # Fallback
    return "SARIF"

# ------------------------------ HTTP helpers -------------------------------

def _dojo_session(cfg: DojoConfig, token: str) -> Tuple[requests.Session, str]:
    s = requests.Session()
    s.headers.update({"Authorization": f"Token {token}"})
    s.verify = cfg.verify_ssl
    return s, cfg.url

def _get_or_create_product(session: requests.Session, base: str, product_name: str) -> Dict[str, Any]:
    r = session.get(f"{base}/api/v2/products/", params={"name": product_name})
    r.raise_for_status()
    for p in r.json().get("results", []):
        if p.get("name") == product_name:
            return p
    r = session.post(f"{base}/api/v2/products/", data={"name": product_name})
    r.raise_for_status()
    return r.json()

def _detect_scm_type(repo_url: str) -> str:
    from urllib.parse import urlparse
    host = urlparse(repo_url).netloc.lower()
    if "github" in host:
        return "github"
    if "gitlab" in host:
        return "gitlab"
    if "bitbucket.org" in host:
        return "bitbucket-cloud"
    if "bitbucket" in host:
        return "bitbucket-server"
    if "gitea" in host:
        return "gitea"
    if "codeberg" in host:
        return "codeberg"
    if "dev.azure.com" in host or "visualstudio.com" in host:
        return "azure"
    return "generic"

def _build_source_link(repo_url: str, file_path: str, ref: Optional[str]) -> Optional[str]:
    """Build a repository link WITHOUT a line anchor (#L)."""
    if not repo_url or not file_path:
        return None
    scm = _detect_scm_type(repo_url)
    ref = ref or "master"
    fp = file_path.lstrip("/")

    if scm == "github":
        return f"{repo_url.rstrip('/')}/blob/{ref}/{fp}"
    if scm == "gitlab":
        return f"{repo_url.rstrip('/')}/-/blob/{ref}/{fp}"
    if scm == "bitbucket-cloud":
        return f"{repo_url.rstrip('/')}/src/{ref}/{fp}"
    if scm == "bitbucket-server":
        return f"{repo_url.rstrip('/')}/browse/{fp}?at={ref}"
    if scm in ("gitea", "codeberg"):
        return f"{repo_url.rstrip('/')}/src/{ref}/{fp}"
    if scm == "azure":
        return f"{repo_url.rstrip('/')}/?path=/{fp}&version=GC{ref}"
    return f"{repo_url.rstrip('/')}/blob/{ref}/{fp}"

def _ensure_engagement(session: requests.Session, base: str, product_id: int, name: str,
                       repo_url: Optional[str], branch_tag: Optional[str], commit_hash: Optional[str],
                       engagement_type: str = "CI/CD") -> Dict[str, Any]:
    r = session.get(f"{base}/api/v2/engagements/", params={"product": product_id, "name": name})
    r.raise_for_status()
    results = r.json().get("results", [])
    if results:
        eng = results[0]
        patch = {}
        if repo_url and eng.get("repo") != repo_url:
            patch["repo"] = repo_url
        if branch_tag and eng.get("branch_tag") != branch_tag:
            patch["branch_tag"] = branch_tag
        if commit_hash and eng.get("commit_hash") != commit_hash:
            patch["commit_hash"] = commit_hash
        if patch:
            r = session.patch(f"{base}/api/v2/engagements/{eng['id']}/", data=patch)
            r.raise_for_status()
            return r.json()
        return eng

    data = {"name": name, "product": product_id, "engagement_type": engagement_type}
    if repo_url:
        data["repo"] = repo_url
    if branch_tag:
        data["branch_tag"] = branch_tag
    if commit_hash:
        data["commit_hash"] = commit_hash
    r = session.post(f"{base}/api/v2/engagements/", data=data)
    r.raise_for_status()
    return r.json()

def _get_findings_for_test(session: requests.Session, base: str, test_id: int) -> List[int]:
    ids: List[int] = []
    limit, offset = 200, 0
    while True:
        r = session.get(f"{base}/api/v2/findings/", params={"test": test_id, "limit": limit, "offset": offset})
        r.raise_for_status()
        j = r.json()
        ids.extend([f["id"] for f in j.get("results", [])])
        if not j.get("next"):
            break
        offset += limit
    return ids

def _get_finding(session: requests.Session, base: str, finding_id: int) -> Dict[str, Any]:
    r = session.get(f"{base}/api/v2/findings/{finding_id}/")
    r.raise_for_status()
    return r.json()

def _post_finding_meta(session: requests.Session, base: str, finding_id: int, name: str, value: str) -> Dict[str, Any]:
    r = session.get(f"{base}/api/v2/finding_meta/", params={"finding": finding_id, "name": name})
    r.raise_for_status()
    j = r.json()
    if j.get("count"):
        meta_id = j["results"][0]["id"]
        r = session.patch(f"{base}/api/v2/finding_meta/{meta_id}/", data={"name": name, "value": value})
        r.raise_for_status()
        return r.json()
    r = session.post(f"{base}/api/v2/finding_meta/", data={"finding": str(finding_id), "name": name, "value": value})
    r.raise_for_status()
    return r.json()

def _derive_engagement_name(analyzer_name: str, commit: Optional[str], name_mode = "analyzer-sha") -> str:
    """Generate engagement name according to NAME_MODE."""
    short = (commit or "")[:8] if commit else None
    if name_mode == "analyzer":
        return analyzer_name
    # default
    return "-".join([x for x in [analyzer_name, short] if x]) or analyzer_name

def upload_report(
    analyzer_name: str,
    dojo_cfg: Dict[str, Any] | DojoConfig,
    dojo_token: str,
    product_name: str,
    scan_type: str,
    report_path: str,
    repo_path: str = "."
) -> Dict[str, Any]:
    """
    Upload the report and enrich all created findings with finding_meta['sourcefile_link'].
    - analyzer_name: logical analyzer key (used in analyzers.yaml and for engagement naming)
    - dojo_cfg: dict like loaded YAML or DojoConfig
    - dojo_token: API token
    - product_name: Product to import into (created if missing)
    - scan_type: Dojo scan type (you already compute it outside)
    - report_path: path to the analyzer report
    - repo_path: local Git repo path for deriving repo_url/branch/commit

    Returns: import JSON extended with 'enriched_findings' and 'engagement' meta.
    """
    cfg = dojo_cfg if isinstance(dojo_cfg, DojoConfig) else DojoConfig(
        url=(dojo_cfg.get("defectdojo", {}) or {}).get("url", ""),
        verify_ssl=bool((dojo_cfg.get("defectdojo", {}) or {}).get("verify_ssl", True)),
        minimum_severity=(dojo_cfg.get("defectdojo", {}) or {}).get("minimum_severity", "Info"),
    )
    session, base = _dojo_session(cfg, dojo_token)

    # 1) product
    product = _get_or_create_product(session, base, product_name)

    # 2) repo info from local Git
    repo_url = branch_tag = commit_hash = None
    try:
        info = read_repo_params(repo_path or os.environ.get("GIT_REPO_PATH", "."))
        repo_url, branch_tag, commit_hash = info.repo_url, info.branch_tag, info.commit_hash
    except Exception:
        pass  # best-effort

    # 3) engagement
    engagement_name = _derive_engagement_name(analyzer_name, branch_tag, commit_hash)
    engagement = _ensure_engagement(session, base, product["id"], engagement_name, repo_url, branch_tag, commit_hash, "CI/CD")

    # 4) import-scan
    data = {
        "scan_type": scan_type,
        "engagement": str(engagement["id"]),
        "minimum_severity": cfg.minimum_severity,
        "active": "true",
        "verified": "false",
        "close_old_findings": "false",
    }
    if commit_hash:
        data["build_id"] = commit_hash

    with open(report_path, "rb") as f:
        files = {"file": (os.path.basename(report_path), f, "application/octet-stream")}
        r = session.post(f"{base}/api/v2/import-scan/", data=data, files=files)
        r.raise_for_status()
        import_resp = r.json()

    # 5) collect finding IDs produced by this import
    finding_ids: List[int] = []
    if isinstance(import_resp, dict):
        if "findings" in import_resp and isinstance(import_resp["findings"], list):
            finding_ids = [fi.get("id") if isinstance(fi, dict) else fi for fi in import_resp["findings"]]
        elif "test" in import_resp and import_resp.get("test"):
            test_id = import_resp["test"]
            if isinstance(test_id, dict):
                test_id = test_id.get("id")
            if isinstance(test_id, int):
                finding_ids = _get_findings_for_test(session, base, test_id)

    # 6) enrich each finding with sourcefile_link
    enriched = 0
    ref = commit_hash or branch_tag
    for fid in finding_ids:
        try:
            f = _get_finding(session, base, fid)
            file_path = f.get("file_path") or ""
            link = _build_source_link(repo_url or "", file_path, ref)
            if link:
                _post_finding_meta(session, base, fid, "sourcefile_link", link)
                enriched += 1
        except Exception:
            continue

    import_resp["enriched_findings"] = enriched
    import_resp["engagement"] = {"id": engagement["id"], "name": engagement_name}
    return import_resp

def upload_results(
    config_path: str,
    analyzers_cfg_path: Optional[str],
    product_name: str,
    analyzer_name: str,
    report_path: str,
    repo_path: str = "."
) -> Dict[str, Any]:
    """
    - Loads Dojo config + token from env
    - Resolves scan_type (analyzers.yaml or heuristics)
    - Calls upload_report() which will also enrich findings with sourcefile_link
    """
    cfg = load_dojo_config(config_path)
    token = os.environ.get("DEFECTDOJO_TOKEN") or ""
    if not token:
        raise ValueError("Missing DEFECTDOJO_TOKEN environment variable.")

    scan_type = resolve_scan_type(analyzers_cfg_path, analyzer_name, report_path)
    return upload_report(
        analyzer_name=analyzer_name,
        dojo_cfg=cfg,
        dojo_token=token,
        product_name=product_name,
        scan_type=scan_type,
        report_path=report_path,
        repo_path=repo_path,
    )
