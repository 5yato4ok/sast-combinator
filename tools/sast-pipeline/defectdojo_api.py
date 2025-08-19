#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DefectDojo upload helper (directory-based).

- Reads DefectDojo config from YAML + env overrides (DEFECTDOJO_TOKEN required).
- Resolves scan_type (cached) using analyzers.yaml (if provided).
- For each report:
    * Ensures Product by name.
    * Ensures Engagement (name based on YAML 'name_mode': analyzer | analyzer-branch | analyzer-branch-sha).
    * Auto-fills repo/branch/commit from local Git (repo_path).
    * Imports the report.
    * Adds finding_meta['sourcefile_link'] for findings created by this import.
- Returns a list[ImportResult] (one per report).

All comments are in English.
"""

from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Tuple
from repo_info import read_repo_params
from dotenv import load_dotenv
import config_utils
import urllib3

import requests

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

# ------------------------------ logging ------------------------------------

logger = logging.getLogger("defectdojo")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# ------------------------------ configuration ------------------------------

@dataclass
class DojoConfig:
    url: str
    verify_ssl: bool = True
    minimum_severity: str = "Info"
    name_mode: str = "analyzer-sha"  # analyzer | analyzer-branch | analyzer-branch-sha | analyzer-sha

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
    name_mode = dd.get("name_mode", "analyzer-sha")
    if name_mode not in ("analyzer", "analyzer-branch", "analyzer-sha"):
        logger.warning("Unknown name_mode '%s'; falling back to 'analyzer-sha'", name_mode)
        name_mode = "analyzer-sha"
    return DojoConfig(url=url.rstrip("/"), verify_ssl=verify_ssl, minimum_severity=minimum_severity, name_mode=name_mode)

# ------------------------------ analyzers + scan_type (cached) -------------
def resolve_scan_type(analyzer) -> str:
    ot = analyzer.get("output_type", "SARIF")
    if ot.lower() in ("xml", "generic-xml"):
        return "Generic XML Import"
    return ot

# ------------------------------ link builder --------------------------------

class LinkBuilder:
    """Builds repository links without line anchors, based on repo host and ref."""
    @staticmethod
    def _scm_type(repo_url: str) -> str:
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

    def build(self, repo_url: str, file_path: str, ref: Optional[str]) -> Optional[str]:
        if not repo_url or not file_path:
            return None
        scm = self._scm_type(repo_url)
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

# ------------------------------ HTTP helpers --------------------------------

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
    r = session.post(f"{base}/api/v2/products/", json={"name": product_name})
    r.raise_for_status()
    return r.json()

def _ensure_engagement(session: requests.Session, base: str, product_name: int, name: str,
                       repo_url: Optional[str], branch_tag: Optional[str], commit_hash: Optional[str],
                       engagement_type: str = "CI/CD") -> Dict[str, Any]:
    r = session.get(f"{base}/api/v2/engagements/", params={"product_name": product_name, "name": name})
    r.raise_for_status()
    results = r.json().get("results", [])
    if results:
        eng = results[0]
        patch = {}
        if repo_url and eng.get("source_code_management_uri") != repo_url:
            patch["source_code_management_uri"] = repo_url
        if branch_tag and eng.get("branch_tag") != branch_tag:
            patch["branch_tag"] = branch_tag
        if commit_hash and eng.get("commit_hash") != commit_hash:
            patch["commit_hash"] = commit_hash
        if patch:
            r = session.patch(f"{base}/api/v2/engagements/{eng['id']}/", data=patch)
            r.raise_for_status()
            eng = r.json()
        return eng

    data = {"name": name, "product_name": product_name, "engagement_type": engagement_type}
    if repo_url:
        data["source_code_management_uri"] = repo_url
    if branch_tag:
        data["branch_tag"] = branch_tag
    if commit_hash:
        data["commit_hash"] = commit_hash
    r = session.post(f"{base}/api/v2/engagements/", json=data)
    r.raise_for_status()
    return r.json()

def _get_findings_for_test(session: requests.Session, base: str, test_id: int) -> List[Dict[str, Any]]:
    """Return full finding objects for a given test (avoid N+1)."""
    items: List[Dict[str, Any]] = []
    limit, offset = 200, 0
    while True:
        r = session.get(f"{base}/api/v2/findings/", params={"test": test_id, "limit": limit, "offset": offset})
        r.raise_for_status()
        j = r.json()
        items.extend(j.get("results", []))
        if not j.get("next"):
            break
        offset += limit
    return items

def _post_finding_meta(session: requests.Session, base: str, finding_id: int, name: str, value: str):
    url = f"{base.rstrip('/')}/api/v2/findings/{finding_id}/metadata/"
    r = session.post(url, json={"name": name, "value": value})
    r.raise_for_status()
    return r.json()

# ------------------------------ Repo info -----------------------------------

def _read_repo_info(repo_path: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Best-effort fetch of (repo_url, branch_tag, commit_hash) from local Git via repo_info.read_repo_params."""
    try:
        info = read_repo_params(repo_path)
        return info.repo_url, info.branch_tag, info.commit_hash
    except Exception as e:
        logger.error("Repo info unavailable for '%s': %s", repo_path, e)
        return None, None, None

# ------------------------------ ImportResult --------------------------------

@dataclass
class ImportResult:
    engagement_id: int
    engagement_name: str
    test_id: Optional[int]
    imported_findings: int
    enriched_count: int
    raw: Dict[str, Any]

# ------------------------------ core upload ---------------------------------

def _derive_engagement_name(analyzer_name: str, branch: Optional[str], commit: Optional[str], name_mode: str) -> str:
    short = (commit or "")[:8] if commit else None
    if name_mode == "analyzer":
        return analyzer_name
    if name_mode == "analyzer-branch":
        return "-".join([x for x in [analyzer_name, branch] if x])
    return "-".join([x for x in [analyzer_name, short] if x]) or analyzer_name


def upload_report(
    analyzer_name: str,
    dojo_cfg: Dict[str, Any] | DojoConfig,
    dojo_token: str,
    product_name: str,
    scan_type: str,
    report_path: str,
    repo_path: str = "."
) -> ImportResult:
    """Upload a single report and enrich findings with finding_meta['sourcefile_link'] (returns ImportResult)."""
    if not os.path.isfile(report_path):
        raise FileNotFoundError(f"Report path does not exist: {report_path}")

    cfg = dojo_cfg if isinstance(dojo_cfg, DojoConfig) else DojoConfig(
        url=(dojo_cfg.get("defectdojo", {}) or {}).get("url", ""),
        verify_ssl=bool((dojo_cfg.get("defectdojo", {}) or {}).get("verify_ssl", True)),
        minimum_severity=(dojo_cfg.get("defectdojo", {}) or {}).get("minimum_severity", "Info"),
        name_mode=(dojo_cfg.get("defectdojo", {}) or {}).get("name_mode", "analyzer-branch-sha"),
    )
    session, base = _dojo_session(cfg, dojo_token)

    # Product
    product = _get_or_create_product(session, base, product_name)
    logger.info("Using product '%s' (id=%s)", product_name, product["id"])

    # Repo info
    repo_url, branch_tag, commit_hash = _read_repo_info(repo_path or os.environ.get("GIT_REPO_PATH", "."))

    # Engagement
    engagement_name = _derive_engagement_name(analyzer_name, branch_tag, commit_hash, cfg.name_mode)
    engagement = _ensure_engagement(session, base, product["name"], engagement_name, repo_url, branch_tag, commit_hash, "CI/CD")
    logger.info("Using engagement '%s' (id=%s)", engagement_name, engagement["id"])

    # Import
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
    logger.info("Import finished for %s", analyzer_name)

    # Collect findings
    findings: List[Dict[str, Any]] = []
    test_id: Optional[int] = None
    if isinstance(import_resp, dict):
        if "test" in import_resp and import_resp.get("test"):
            test_id = import_resp["test"]["id"] if isinstance(import_resp["test"], dict) else import_resp["test"]
            findings = _get_findings_for_test(session, base, int(test_id))
        elif "findings" in import_resp and isinstance(import_resp["findings"], list):
            ids = [fi.get("id") if isinstance(fi, dict) else fi for fi in import_resp["findings"]]
            for fid in ids:
                r = session.get(f"{base}/api/v2/findings/{fid}/")
                r.raise_for_status()
                findings.append(r.json())

    imported_count = len(findings)

    # Enrich metadata
    linker = LinkBuilder()
    enriched = 0
    ref = commit_hash or branch_tag
    logger.info(f"Start enriching {len(findings)} findings")
    for f in findings:
        try:
            file_path = f.get("file_path") or ""
            link = linker.build(repo_url or "", file_path, ref)
            if link:
                _post_finding_meta(session, base, f["id"], "sourcefile_link", link)
                enriched += 1
        except Exception as e:
            logger.warning("Failed to enrich finding %s: %s", f.get("id"), e)

    logger.info("Enriched findings: %s/%s", enriched, imported_count)
    return ImportResult(
        engagement_id=engagement["id"],
        engagement_name=engagement_name,
        test_id=test_id,
        imported_findings=imported_count,
        enriched_count=enriched,
        raw=import_resp,
    )

# ------------------------------ directory entry -----------------------------

def upload_results(
    output_dir: str,
    analyzers_cfg_path: Optional[str],
    product_name: str,
    dojo_config_path: str,
    repo_path: str = "."
) -> List[ImportResult]:
    cfg = load_dojo_config(dojo_config_path)
    token = os.environ.get("DEFECTDOJO_TOKEN") or ""
    if not token:
        raise ValueError("Missing DEFECTDOJO_TOKEN environment variable.")
    if not os.path.isdir(output_dir):
        raise NotADirectoryError(f"Reports directory does not exist: {output_dir}")

    results: List[ImportResult] = []
    cfg_helper = config_utils.AnalyzersConfigHelper(analyzers_cfg_path)
    for analyzer in cfg_helper.get_analyzers():
        analyzer_name = analyzer.get("name")
        report_path = os.path.join(output_dir, cfg_helper.get_analyzer_result_file_name(analyzer))
        scan_type = resolve_scan_type(analyzer)
        logger.info("Processing report: %s (analyzer=%s, scan_type=%s)", report_path, analyzer_name, scan_type)

        res = upload_report(
            analyzer_name=analyzer_name,
            dojo_cfg=cfg,
            dojo_token=token,
            product_name=product_name,
            scan_type=scan_type,
            report_path=report_path,
            repo_path=repo_path,
        )
        results.append(res)

    return results



def enrich_existing_findings(
    dojo_config_path: str,
    product_name: Optional[str] = None,
    only_missing: bool = True,
) -> int:
    """
    Enrich existing findings with finding_meta['sourcefile_link'] using repo/ref from their Engagement.
    Uses `related_fields=true` to fetch engagement data inline (no extra GETs per finding).
    Skips findings when engagement or repo/ref info is unavailable.
    """
    cfg = load_dojo_config(dojo_config_path)
    token = os.environ.get("DEFECTDOJO_TOKEN") or ""
    if not token:
        raise ValueError("Missing DEFECTDOJO_TOKEN environment variable.")

    session, base = _dojo_session(cfg, token)
    linker = LinkBuilder()

    params = {"limit": 200, "related_fields": "true"}
    if product_name is not None:
        params["product_name"] = product_name

    updated = 0
    offset = 0

    while True:
        page_params = dict(params)
        page_params["offset"] = offset
        r = session.get(f"{base}/api/v2/findings/", params=page_params)
        r.raise_for_status()
        j = r.json()
        findings = j.get("results", [])

        if not findings:
            break
        total_num = len(findings)
        for f in findings:
            try:
                fid = f.get("id")
                file_path = f.get("file_path") or ""
                if not fid or not file_path:
                    continue

                # Pull engagement from related_fields.test.engagement
                rf = f.get("related_fields") or {}
                test_rf = rf.get("test") or {}
                engagement = test_rf.get("engagement") or {}
                repo_url = engagement.get("source_code_management_uri", None)
                if not repo_url:
                    full_engagement_r = session.get(f"{base}/api/v2/engagements/{engagement["id"]}")
                    full_engagement_r.raise_for_status()
                    full_engagement = full_engagement_r.json()
                    repo_url = full_engagement.get("source_code_management_uri", None)
                ref = engagement.get("commit_hash") or engagement.get("branch_tag")
                if not (repo_url and (ref or True)):  # ref may be None, builder will default to master
                    if not repo_url:
                        continue

                if only_missing:
                    mr = session.get(f"{base}/api/v2/findings/{fid}/metadata/")
                    mr.raise_for_status()
                    mr_json = mr.json()
                    if "sourcefile_link" in mr_json:
                        continue

                link = linker.build(repo_url, file_path, ref)
                if not link:
                    continue

                _post_finding_meta(session, base, fid, "sourcefile_link", link)
                updated += 1
                if updated % 100 == 0:
                    logger.info(f"Processed {updated} findings. Left {(total_num - updated)}")

            except Exception as e:
                logger.warning("Failed to enrich finding id=%s: %s", f.get("id"), e)
                continue

        if not j.get("next"):
            break
        offset += params["limit"]

    logger.info("Bulk enrichment complete. Updated findings: %s", updated)
    return updated


if __name__ == "__main__":
    load_dotenv(dotenv_path=".env")
    enrich_existing_findings(dojo_config_path="config/defectdojo.yaml",product_name="VulnerableSharpApp", only_missing=True)
    enrich_existing_findings(dojo_config_path="config/defectdojo.yaml",product_name="juicy_shop", only_missing=True)
    enrich_existing_findings(dojo_config_path="config/defectdojo.yaml", product_name="nx_open", only_missing=True)