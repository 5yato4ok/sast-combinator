#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from repo_info import read_repo_params, RepoParams
from requests.adapters import HTTPAdapter
from typing import Any, Dict, Optional, List, Tuple
from datetime import date, timedelta
import json
import logging
import os
import requests
import threading
import argparse
from dotenv import load_dotenv
from urllib3.util.retry import Retry
import urllib3
import config_utils

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

# ------------------------------ logging ------------------------------------

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=getattr(logging, "INFO", logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === Parallel HTTP helpers ===
_thread_local = threading.local()

def _make_session_like(proto: requests.Session) -> requests.Session:
    s = requests.Session()
    # Copy critical session attributes
    s.headers.update(proto.headers)
    s.cookies.update(proto.cookies)
    try:
        s.verify = proto.verify
    except Exception:
        pass
    try:
        s.cert = proto.cert
    except Exception:
        pass
    try:
        s.trust_env = proto.trust_env
    except Exception:
        pass
    # Copy proxies/auth if defined
    if getattr(proto, "proxies", None):
        s.proxies.update(proto.proxies)
    if getattr(proto, "auth", None):
        s.auth = proto.auth

    # Beef up pool size & retries for concurrency
    retry = Retry(total=3, backoff_factor=0.3, status_forcelist=(429, 500, 502, 503, 504))
    adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

def _tls_session(proto: requests.Session) -> requests.Session:
    """Thread-local clone of the base session."""
    if not hasattr(_thread_local, "session"):
        _thread_local.session = _make_session_like(proto)
    return _thread_local.session

def _fetch_engagement(base: str, eng_id: int, proto_sess: requests.Session, cache: dict, cache_lock: threading.Lock) -> dict:
    with cache_lock:
        if eng_id in cache:
            return cache[eng_id]
    s = _tls_session(proto_sess)
    r = s.get(f"{base}/api/v2/engagements/{eng_id}/")
    r.raise_for_status()
    data = r.json()
    with cache_lock:
        cache[eng_id] = data
    return data

def _has_sourcefile_link(base: str, finding_id: int, proto_sess: requests.Session) -> bool:
    s = _tls_session(proto_sess)
    r = s.get(f"{base}/api/v2/findings/{finding_id}/metadata/", params={"name": "sourcefile_link"})
    r.raise_for_status()
    js = r.json()
    if isinstance(js, dict) and "results" in js:
        return any(m.get("name") == "sourcefile_link" for m in js.get("results", []))
    if isinstance(js, list):
        return any(m.get("name") == "sourcefile_link" for m in js)
    return False

def _delete_finding(session: requests.Session, base: str, finding_id: int):
    logger.warning(f"Deleting {finding_id}")
    r = session.delete(f"{base}/api/v2/findings/{finding_id}/")
    # DefectDojo returns 204 on successful delete
    if r.status_code in (200, 202, 204):
        return
    else:
        try:
            r.raise_for_status()
        except Exception as e:
            if logger:
                logger.warning("Failed to delete finding id=%s: %s", finding_id, e)

def _post_finding_meta_json(proto_sess: requests.Session, base: str, finding_id: int, name: str, value: str) -> None:
    s = _tls_session(proto_sess)
    url = f"{base.rstrip('/')}/api/v2/findings/{finding_id}/metadata/"
    data= {"name": name, "value": value}
    logger.debug(f"Attempt to enrich finding : {data}")
    r = s.post(url, json=data)
    r.raise_for_status()

def _process_one_finding(
    f: dict,
    base: str,
    linker,
    only_missing: bool,
    proto_sess: requests.Session,
    eng_cache: dict,
    eng_cache_lock: threading.Lock,
    logger=None,
) -> int:
    try:
        fid = f.get("id")
        file_path = f.get("file_path") or ""
        if not fid or not file_path:
            return 0

        rf = f.get("related_fields") or {}
        test_rf = rf.get("test") or {}
        engagement = test_rf.get("engagement") or {}
        repo_url = engagement.get("source_code_management_uri")
        ref = engagement.get("commit_hash") or engagement.get("branch_tag")

        if not repo_url:
            eng_id = engagement.get("id")
            if not eng_id:
                return 0
            full_eng = _fetch_engagement(base, eng_id, proto_sess, eng_cache, eng_cache_lock)
            repo_url = full_eng.get("source_code_management_uri")
            ref = ref or full_eng.get("commit_hash") or full_eng.get("branch_tag")
            if not repo_url:
                return 0

        if only_missing and _has_sourcefile_link(base, fid, proto_sess):
            return 0

        link = linker.build(repo_url, file_path, ref)
        if not link:
            return 0

        _post_finding_meta_json(proto_sess, base, fid, "sourcefile_link", link)
        return 1
    except Exception as e:
        logger.warning("Failed to enrich finding id=%s: %s", f.get("id"), e)
        return 0

# ------------------------------ configuration ------------------------------

@dataclass
class DojoConfig:
    url: str
    verify_ssl: bool = False
    minimum_severity: str = "Info"
    name_mode: str = "analyzer-sha"  # analyzer | analyzer-branch | analyzer-branch-sha | analyzer-sha
    engagement_status: str = "In Progress"

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
    engagement_status = os.environ.get("DEFECTDOJO_DEFAULT_ENGAGEMENT_STATUS") or dd.get("engagement_status", "In Progress")
    return DojoConfig(url=url.rstrip("/"), verify_ssl=verify_ssl, minimum_severity=minimum_severity, name_mode=name_mode, engagement_status=engagement_status)

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
        file_path = file_path.replace("file://","")
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

    def remote_link_exists(self, url: str, timeout: int = 5) -> bool | None:
        """
          True  – GET 200 или 3xx (file exist),
          False – 404 (file not exist),
          None  – some other mistake.
        """
        try:
            r = requests.get(url, allow_redirects=True, timeout=timeout)
            if r.status_code == 200:
                return True
            if 300 <= r.status_code < 400:
                return True
            if r.status_code == 404:
                logger.warning(f"Url is not valid repo file: {url}")
                return False
            return None
        except requests.RequestException:
            return None

# ------------------------------ HTTP helpers --------------------------------

def _dojo_session(cfg: DojoConfig, token: str) -> Tuple[requests.Session, str]:
    s = requests.Session()
    s.headers.update({"Authorization": f"Token {token}"})
    s.verify = cfg.verify_ssl
    return s, cfg.url


def _get_product_by_name(session: requests.Session, base: str, product_name: str) -> Optional[dict]:
    """Return product object with exact name match, or None."""
    limit, offset = 200, 0
    while True:
        r = session.get(f"{base}/api/v2/products/", params={"name": product_name, "limit": limit, "offset": offset})
        r.raise_for_status()
        data = r.json()
        for p in data.get("results", []):
            if p.get("name") == product_name:
                return p
        if not data.get("next"):
            break
        offset += limit
    return None

def _iter_findings_for_product(session: requests.Session, base: str, product_name: str):
    """Yield full finding dicts for a given product."""
    limit, offset = 200, 0
    while True:
        r = session.get(f"{base}/api/v2/findings/", params={"product_name": product_name, "limit": limit, "offset": offset})
        r.raise_for_status()
        data = r.json()
        for f in data.get("results", []):
            yield f
        if not data.get("next"):
            break
        offset += limit

def _get_or_create_product(session: requests.Session, base: str, product_name: str) -> Dict[str, Any]:
    product = _get_product_by_name(session, base, product_name)
    if product:
        return product

    r = session.post(f"{base}/api/v2/products/", json={"name": product_name})
    r.raise_for_status()
    return r.json()


def _ensure_engagement(session: requests.Session, base: str, product_id: int, name: str,
                       repo_url: Optional[str], branch_tag: Optional[str], commit_hash: Optional[str],
                       engagement_status: str = "In Progress",
                       engagement_type: str = "CI/CD") -> Dict[str, Any]:
    r = session.get(f"{base}/api/v2/engagements/", params={"product": product_id, "name": name})
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
            r = session.patch(f"{base}/api/v2/engagements/{eng['id']}/", json=patch)
            r.raise_for_status()
            eng = r.json()

        logger.debug(f"Found existing engagement {eng}")
        return eng

    today = date.today()
    tomorrow = today + timedelta(days=1)
    data = {
        "name": name,
        "product": product_id,
        "engagement_type": engagement_type,
        "target_start": today.isoformat(),
        "target_end": tomorrow.isoformat(),
        "status": engagement_status
    }

    if repo_url:
        data["source_code_management_uri"] = repo_url
    if branch_tag:
        data["branch_tag"] = branch_tag
    if commit_hash:
        data["commit_hash"] = commit_hash

    logger.debug(f"Attempt to create engagement {data}")
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
    dojo_cfg: DojoConfig,
    dojo_token: str,
    product_name: str,
    scan_type: str,
    report_path: str,
    repo_params: RepoParams
) -> ImportResult:
    """Upload a single report and enrich findings with finding_meta['sourcefile_link'] (returns ImportResult)."""
    if not os.path.isfile(report_path):
        raise FileNotFoundError(f"Report path does not exist: {report_path}")

    session, base = _dojo_session(dojo_cfg, dojo_token)

    # Product
    product = _get_or_create_product(session, base, product_name)
    logger.info("Using product '%s' (id=%s)", product_name, product["id"])

    # Engagement
    engagement_name = _derive_engagement_name(analyzer_name, repo_params.branch_tag, repo_params.commit_hash,
                                              dojo_cfg.name_mode)
    engagement = _ensure_engagement(session, base, product["id"], engagement_name, repo_params.repo_url,
                                    repo_params.branch_tag, repo_params.commit_hash, dojo_cfg.engagement_status,
                                    "CI/CD")
    logger.info("Using engagement '%s' (id=%s)", engagement_name, engagement["id"])

    # Import
    data = {
        "scan_type": scan_type,
        "engagement": str(engagement["id"]),
        "minimum_severity": dojo_cfg.minimum_severity,
        "active": "true",
        "verified": "false",
        "close_old_findings": "false",
    }
    if repo_params.commit_hash:
        data["build_id"] = repo_params.commit_hash

    logger.debug(f"Attempt to upload report {data} and file {report_path}")
    if os.path.getsize(report_path) == 0:
        raise ValueError(f"File {report_path} is empty")
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
    ref = repo_params.commit_hash or repo_params.branch_tag
    logger.info(f"Start enriching {len(findings)} findings")
    # Parallel enrichment of metadata for this report
    _workers = max(1, (os.cpu_count() or 4))
    enriched = 0

    def _process_one(f):
        nonlocal enriched
        try:
            file_path = f.get("file_path") or ""
            link = linker.build(repo_params.repo_url or "", file_path, ref)
            if link:
                if linker.remote_link_exists(link):
                    _post_finding_meta_json(session, base, f["id"], "sourcefile_link", link)
                else:
                    _delete_finding(session, base, f["id"])
                return 1
        except Exception as e:
            logger.warning("Failed to enrich finding %s: %s", f.get("id"), e)
        return 0

    with ThreadPoolExecutor(max_workers=_workers) as ex:
        for res in ex.map(_process_one, findings):
            enriched += res

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
    repo_path: str
) -> List[ImportResult]:
    cfg = load_dojo_config(dojo_config_path)
    token = os.environ.get("DEFECTDOJO_TOKEN") or ""
    if not token:
        raise ValueError("Missing DEFECTDOJO_TOKEN environment variable.")
    if not os.path.isdir(output_dir):
        raise NotADirectoryError(f"Reports directory does not exist: {output_dir}")

    results: List[ImportResult] = []
    cfg_helper = config_utils.AnalyzersConfigHelper(analyzers_cfg_path)
    # Repo info
    repo_params = read_repo_params(repo_path or os.environ.get("GIT_REPO_PATH", "."))
    for analyzer in cfg_helper.get_analyzers():
        analyzer_name = analyzer.get("name")
        report_path = os.path.join(output_dir, cfg_helper.get_analyzer_result_file_name(analyzer))
        if not os.path.exists(report_path):
            logging.error(f"No result on expected path {report_path} for analyzer {analyzer_name}")
            continue
        scan_type = resolve_scan_type(analyzer)
        logger.info("Processing report: %s (analyzer=%s, scan_type=%s)", report_path, analyzer_name, scan_type)

        try:
            res = upload_report(
                analyzer_name=analyzer_name,
                dojo_cfg=cfg,
                dojo_token=token,
                product_name=product_name,
                scan_type=scan_type,
                report_path=report_path,
                repo_params=repo_params
            )
            results.append(res)
        except Exception as exc:
            logger.error(f"Error during uploading report. {exc} Continue")

    return results



def enrich_existing_findings(
    dojo_config_path: str,
    product_name: Optional[str] = None,
    only_missing: bool = True,
    max_workers: Optional[int] = None,
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

    proto_sess, base = _dojo_session(cfg, token)
    linker = LinkBuilder()

    params = {"limit": 200, "related_fields": "true"}
    if product_name is not None:
        params["product_name"] = product_name

    updated_total = 0
    offset = 0

    eng_cache = {}
    eng_cache_lock = threading.Lock()

    if max_workers is None:
        max_workers = max(1, (os.cpu_count() or 4))

    while True:
        page_params = dict(params, offset=offset)
        r = proto_sess.get(f"{base}/api/v2/findings/", params=page_params)
        r.raise_for_status()
        j = r.json()
        findings = j.get("results", [])
        if not findings:
            break

        processed_on_page = 0
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [
                ex.submit(
                    _process_one_finding,
                    f,
                    base,
                    linker,
                    only_missing,
                    proto_sess,
                    eng_cache,
                    eng_cache_lock,
                    logger,
                )
                for f in findings
            ]
            for fut in as_completed(futures):
                processed_on_page += fut.result()
                if processed_on_page and processed_on_page % 100 == 0:
                    logger.info("Processed %d findings on this page", processed_on_page)

        updated_total += processed_on_page
        logger.info("Page done: +%d updated (total: %d)", processed_on_page, updated_total)

        if not j.get("next"):
            break
        offset += params["limit"]

    logger.info("Bulk enrichment complete. Updated findings: %s", updated_total)
    return updated_total

def delete_findings_by_product_and_path_prefix(
    product_name: str = "VulnerableSharpApp",
    path_prefix: str = ".dotnet",
    dojo_cfg_path: str = "config/defectdojo.yaml",
    dry_run: bool = False,
) -> Tuple[int, int]:
    """
    Delete findings for a given product where file_path starts with a prefix.
    Returns (matched_count, deleted_count).
    """
    """
    Delete findings for a given product where file_path starts with a prefix.
    Returns (matched_count, deleted_count).
    """
    logger = logging.getLogger(__name__)

    cfg = load_dojo_config(dojo_cfg_path)
    token = os.environ.get("DEFECTDOJO_TOKEN") or ""
    if not token:
        raise ValueError("Missing DEFECTDOJO_TOKEN")

    session, base_url = _dojo_session(cfg, token)
    product = _get_product_by_name(session, base_url, product_name)
    if not product:
        raise ValueError(f"Product not found: {product_name}")

    to_delete_ids = []
    for f in _iter_findings_for_product(session, base_url, product_name=product["name"]):
        fp = (f.get("file_path") or "").lstrip()
        if path_prefix in fp:
            fid = f.get("id")
            if fid:
                to_delete_ids.append((fid, fp))

    matched = len(to_delete_ids)
    logger.info("Matched %d findings for product '%s' with prefix '%s'",
                matched, product_name, path_prefix)

    if dry_run or matched == 0:
        return matched, 0


    max_workers = max(1, min(8, (os.cpu_count() or 4)))  # не агрессивно

    def _delete_one(fid_fp, base_url, session, logger):
        fid, fp = fid_fp
        try:
            r = session.delete(f"{base_url}/api/v2/findings/{fid}/")
            if r.status_code in (200, 202, 204):
                return 1
            r.raise_for_status()
            return 0
        except Exception as e:
            logger.warning("Failed to delete finding id=%s file_path=%s: %s", fid, fp, e)
            return 0

    processed_on_page = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [
            ex.submit(
                _delete_one,
                f,
                base_url,
                session,
                logger
            )
            for f in to_delete_ids
        ]
        for fut in as_completed(futures):
            processed_on_page += fut.result()
            if processed_on_page and processed_on_page % 100 == 0:
                logger.info("Processed %d findings on this page", processed_on_page)

    if logger:
        logger.info("Matched: %d, Deleted: %d", matched, processed_on_page)
    return matched, processed_on_page


load_dotenv(dotenv_path=".env")
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Build and analyse a project using configured analyzers, "
            "and optionally upload reports to DefectDojo."
        )
    )
    parser.add_argument(
        "--dojo_product_name",
        required=True,
        help=(
            "If provided, upload resulting reports to the specified DefectDojo "
            "product after analysis."
        ),
    )
    parser.add_argument(
        "--results_path",
        required=True,
        help=(
            "Name of product, which will be used for image name. Can be skipped if dojo_product_name is provided"
        ),
    )
    parser.add_argument(
        "--dojo_config",
        required=False,
        default="config/defectdojo.yaml",
        help="Path to the DefectDojo configuration YAML. Defaults to config/defectdojo.yaml.",
    )

    parser.add_argument(
        "--repo_path",
        required=True,
        help="Path to downloaded repository. Usually locates in /tmp/my_project/build-tmp/{project_name}",
    )

    args = parser.parse_args()
    upload_results(args.results_path, 'config/analyzers.yaml', args.dojo_product_name, 'config/defectdojo.yaml',
                   args.repo_path)
