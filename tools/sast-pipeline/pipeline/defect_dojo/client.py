from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, Generator, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
import urllib3

logger = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class DojoConfig:
    url: str
    verify_ssl: bool = False
    minimum_severity: str = "Info"
    name_mode: str = "analyzer-sha"  # analyzer | analyzer-branch | analyzer-sha
    engagement_status: str = "In Progress"


@dataclass
class ImportResult:
    engagement_id: Optional[int]
    engagement_name: Optional[str]
    test_id: Optional[int]
    imported_findings: int
    enriched_count: int
    raw: Dict[str, Any]


# ------------ session helpers ------------
def _clone_session(src: requests.Session) -> requests.Session:
    s = requests.Session()
    s.headers.update(src.headers or {})
    s.verify = src.verify
    try:
        s.trust_env = src.trust_env  # type: ignore[attr-defined]
    except Exception:
        pass
    if getattr(src, "proxies", None):
        s.proxies.update(src.proxies)
    if getattr(src, "auth", None):
        s.auth = src.auth
    # robust adapter
    retry = urllib3.Retry(total=3, backoff_factor=0.3, status_forcelist=(429, 500, 502, 503, 504))
    adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


class DefectDojoClient:
    """Generic client: all REST interactions centralized here."""

    def __init__(self, cfg: DojoConfig, token: str) -> None:
        self.cfg = cfg
        self.base = cfg.url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Token {token}"})
        self.session.verify = cfg.verify_ssl
        # Attach robust adapters to the main session too
        retry = urllib3.Retry(total=3, backoff_factor=0.3, status_forcelist=(429, 500, 502, 503, 504))
        adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    # ---------- Products ----------
    def list_products(self, **params: Any) -> Dict[str, Any]:
        r = self.session.get(f"{self.base}/api/v2/products/", params=params)
        r.raise_for_status()
        return r.json()

    def get_product_by_name(self, product_name: str) -> Optional[Dict[str, Any]]:
        limit, offset = 200, 0
        while True:
            data = self.list_products(name=product_name, limit=limit, offset=offset)
            for p in data.get("results", []):
                if p.get("name") == product_name:
                    return p
            if not data.get("next"):
                break
            offset += limit
        return None

    def create_product(self, product_name: str) -> Dict[str, Any]:
        payload = {"name": product_name, "description": "Created automatically during report import", "prod_type": 1}
        r = self.session.post(f"{self.base}/api/v2/products/", json=payload)
        r.raise_for_status()
        return r.json()

    def get_or_create_product(self, product_name: str) -> Dict[str, Any]:
        return self.get_product_by_name(product_name) or self.create_product(product_name)

    # ---------- Engagements ----------
    def get_engagements(self, **params: Any) -> Dict[str, Any]:
        r = self.session.get(f"{self.base}/api/v2/engagements/", params=params)
        r.raise_for_status()
        return r.json()

    def get_engagement(self, engagement_id: int) -> Dict[str, Any]:
        r = self.session.get(f"{self.base}/api/v2/engagements/{engagement_id}/")
        r.raise_for_status()
        return r.json()

    def patch_engagement(self, engagement_id: int, patch: Dict[str, Any]) -> Dict[str, Any]:
        r = self.session.patch(f"{self.base}/api/v2/engagements/{engagement_id}/", json=patch)
        r.raise_for_status()
        return r.json()

    def create_engagement(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = self.session.post(f"{self.base}/api/v2/engagements/", json=payload)
        r.raise_for_status()
        return r.json()

    def ensure_engagement(self, product_id: int, name: str,
                          repo_url: Optional[str],
                          branch_tag: Optional[str],
                          commit_hash: Optional[str],
                          engagement_status: str = "In Progress",
                          engagement_type: str = "CI/CD") -> Dict[str, Any]:
        data = self.get_engagements(product=product_id, name=name)
        results = data.get("results", [])
        if results:
            eng = results[0]
            patch: Dict[str, Any] = {}
            if repo_url and eng.get("source_code_management_uri") != repo_url:
                patch["source_code_management_uri"] = repo_url
            if branch_tag and eng.get("branch_tag") != branch_tag:
                patch["branch_tag"] = branch_tag
            if commit_hash and eng.get("commit_hash") != commit_hash:
                patch["commit_hash"] = commit_hash
            if patch:
                eng = self.patch_engagement(int(eng["id"]), patch)
            logger.debug(f"Found existing engagement {eng}")
            return eng

        today = date.today()
        tomorrow = today + timedelta(days=1)
        payload = {
            "name": name,
            "product": product_id,
            "engagement_type": engagement_type,
            "target_start": today.isoformat(),
            "target_end": tomorrow.isoformat(),
            "status": engagement_status,
        }
        if repo_url: payload["source_code_management_uri"] = repo_url
        if branch_tag: payload["branch_tag"] = branch_tag
        if commit_hash: payload["commit_hash"] = commit_hash

        logger.debug(f"Attempt to create engagement {payload}")
        return self.create_engagement(payload)

    # ---------- Findings ----------
    def list_findings(self, **params: Any) -> Dict[str, Any]:
        r = self.session.get(f"{self.base}/api/v2/findings/", params=params)
        r.raise_for_status()
        return r.json()

    def iter_findings(self, **params: Any) -> Generator[Dict[str, Any], None, None]:
        limit, offset = params.pop("limit", 200), params.pop("offset", 0)
        while True:
            page = self.list_findings(limit=limit, offset=offset, **params)
            for f in page.get("results", []):
                yield f
            if not page.get("next"):
                break
            offset += limit

    def get_findings_for_test(self, test_id: int) -> List[Dict[str, Any]]:
        return list(self.iter_findings(test=test_id, limit=200))

    def get_finding(self, finding_id: int) -> Dict[str, Any]:
        r = self.session.get(f"{self.base}/api/v2/findings/{finding_id}/")
        r.raise_for_status()
        return r.json()

    def patch_finding(self, finding: Dict[str, Any]) -> Dict[str, Any]:
        fid = finding["id"]
        logger.debug(f"Attempt to patch {finding}")
        r = self.session.patch(f"{self.base}/api/v2/findings/{fid}/", json=finding)
        r.raise_for_status()
        return r.json()

    def delete_finding(self, finding_id: int) -> None:
        logger.warning(f"Deleting {finding_id}")
        r = self.session.delete(f"{self.base}/api/v2/findings/{finding_id}/")
        if r.status_code in (200, 202, 204):
            return
        r.raise_for_status()

    # ---------- Finding metadata ----------
    def has_sourcefile_link(self, finding_id: int) -> bool:
        # Use cloned session to be thread-safe
        s = _clone_session(self.session)
        r = s.get(f"{self.base}/api/v2/findings/{finding_id}/metadata/", params={"name": "sourcefile_link"})
        r.raise_for_status()
        js = r.json()
        if isinstance(js, dict) and "results" in js:
            return any(m.get("name") == "sourcefile_link" for m in js.get("results", []))
        if isinstance(js, list):
            return any(m.get("name") == "sourcefile_link" for m in js)
        return False

    def post_finding_meta_json(self, finding_id: int, name: str, value: str) -> None:
        s = _clone_session(self.session)
        url = f"{self.base.rstrip('/')}/api/v2/findings/{finding_id}/metadata/"
        data = {"name": name, "value": value}
        r = s.post(url, json=data)
        r.raise_for_status()

    # ---------- Engagement fetch (for enrichment) ----------
    def fetch_engagement(self, eng_id: int, cache: dict, cache_lock) -> dict:
        with cache_lock:
            if eng_id in cache:
                return cache[eng_id]
        s = _clone_session(self.session)
        r = s.get(f"{self.base}/api/v2/engagements/{eng_id}/")
        r.raise_for_status()
        data = r.json()
        with cache_lock:
            cache[eng_id] = data
        return data

    # ---------- Importers ----------
    def import_scan(self, engagement_id: int, scan_type: str, report_path: str,
                    minimum_severity: str, build_id: Optional[str] = None) -> Dict[str, Any]:
        data = {
            "scan_type": scan_type,
            "engagement": str(engagement_id),
            "minimum_severity": minimum_severity,
            "active": "true",
            "verified": "false",
            "close_old_findings": "false",
        }
        if build_id:
            data["build_id"] = build_id
        with open(report_path, "rb") as fh:
            files = {"file": (os.path.basename(report_path), fh, "application/octet-stream")}
            r = self.session.post(f"{self.base}/api/v2/import-scan/", data=data, files=files)
            r.raise_for_status()
            return r.json()
