"""Backward-compatible function layer (exact signatures, same REST semantics)."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml  # type: ignore

from pipeline.config_utils import AnalyzersConfigHelper  # import from parent as requested
from .client import DojoConfig, DefectDojoClient, ImportResult
from .sast_client import SastPipelineDDClient
from .repo_info import read_repo_params  # type: ignore

logger = logging.getLogger(__name__)


def load_dojo_config(config_path: str) -> DojoConfig:
    """Load YAML config exactly like original (with env overrides)."""
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    dd = data.get("defectdojo", {}) or {}
    url = os.environ.get("DEFECTDOJO_URL") or dd.get("url") or ""
    if not url:
        raise ValueError("Missing DefectDojo URL (defectdojo.url or DEFECTDOJO_URL).")

    def _parse_bool(v: Optional[str], default: bool) -> bool:
        if v is None:
            return default
        return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}

    verify_ssl = _parse_bool(os.environ.get("DEFECTDOJO_VERIFY_SSL"), bool(dd.get("verify_ssl", True)))
    minimum_severity = os.environ.get("DEFECTDOJO_MIN_SEVERITY") or dd.get("minimum_severity", "Info")
    name_mode = dd.get("name_mode", "analyzer-sha")
    if name_mode not in ("analyzer", "analyzer-branch", "analyzer-sha"):
        logger.warning("Unknown name_mode '%s'; falling back to 'analyzer-sha'", name_mode)
        name_mode = "analyzer-sha"
    engagement_status = os.environ.get("DEFECTDOJO_DEFAULT_ENGAGEMENT_STATUS") or dd.get("engagement_status", "In Progress")
    return DojoConfig(url=url.rstrip("/"), verify_ssl=verify_ssl, minimum_severity=minimum_severity,
                      name_mode=name_mode, engagement_status=engagement_status)


# analyzers + scan_type
def resolve_scan_type(analyzer) -> str:
    ot = analyzer.get("output_type", "SARIF")
    if ot.lower() in ("xml", "generic-xml"):
        return "Generic XML Import"
    return ot


# Public API: identical signature
def upload_results(
    output_dir: str,
    analyzers_cfg_path: Optional[str],
    product_name: str,
    dojo_config_path: str,
    repo_path: str,
    trim_path: str
) -> List[ImportResult]:
    cfg = load_dojo_config(dojo_config_path)
    token = os.environ.get("DEFECTDOJO_TOKEN") or ""
    if not token:
        raise ValueError("Missing DEFECTDOJO_TOKEN environment variable.")
    if not os.path.isdir(output_dir):
        raise NotADirectoryError(f"Reports directory does not exist: {output_dir}")

    results: List[ImportResult] = []
    cfg_helper = AnalyzersConfigHelper(analyzers_cfg_path)

    # Repo info
    repo_params = read_repo_params(repo_path or os.environ.get("GIT_REPO_PATH", ".."))
    client = SastPipelineDDClient(cfg, token)

    for analyzer in cfg_helper.get_analyzers():
        analyzer_name = analyzer.get("name")
        report_path = os.path.join(output_dir, cfg_helper.get_analyzer_result_file_name(analyzer))
        if not os.path.exists(report_path):
            logging.error(f"No result on expected path {report_path} for analyzer {analyzer_name}")
            continue
        scan_type = resolve_scan_type(analyzer)
        logger.info("Processing report: %s (analyzer=%s, scan_type=%s)", report_path, analyzer_name, scan_type)

        try:
            res = client.upload_report(
                analyzer_name=analyzer_name,
                product_name=product_name,
                scan_type=scan_type,
                report_path=report_path,
                repo_params=repo_params,
                trim_path=trim_path
            )
            results.append(res)
        except Exception as exc:
            logger.error(f"Error during uploading report. {exc} Continue")

    return results


# Public API: identical signature
def enrich_existing_findings(
    dojo_config_path: str,
    product_name: Optional[str] = None,
    only_missing: bool = True,
    max_workers: Optional[int] = None,
) -> int:
    cfg = load_dojo_config(dojo_config_path)
    token = os.environ.get("DEFECTDOJO_TOKEN") or ""
    if not token:
        raise ValueError("Missing DEFECTDOJO_TOKEN environment variable.")

    client = SastPipelineDDClient(cfg, token)
    return client.enrich_existing(product_name=product_name, only_missing=only_missing, max_workers=max_workers)


# Public API: identical signature
def delete_findings_by_product_and_path_prefix(
    product_name: str = "VulnerableSharpApp",
    path_prefix: str = ".dotnet",
    dojo_cfg_path: str = "../config/defectdojo.yaml",
    dry_run: bool = False,
) -> Tuple[int, int]:
    cfg = load_dojo_config(dojo_cfg_path)
    token = os.environ.get("DEFECTDOJO_TOKEN") or ""
    if not token:
        raise ValueError("Missing DEFECTDOJO_TOKEN")

    client = SastPipelineDDClient(cfg, token)
    matched = 0
    items: List[Tuple[int, str]] = []
    for f in client.iter_findings(product_name=product_name, limit=200):
        fid = int(f.get("id"))
        fp = (f.get("file_path") or "").lstrip()
        if path_prefix in fp:
            matched += 1
            items.append((fid, fp))

    logger.info("Matched %d findings for product '%s' with prefix '%s'", matched, product_name, path_prefix)
    if dry_run or matched == 0:
        return matched, 0

    # Not aggressive (mirror original)
    max_workers = max(1, min(8, (os.cpu_count() or 4)))

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

    processed = 0
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_delete_one, item, client.base, client.session, logger) for item in items]
        for fut in as_completed(futures):
            processed += fut.result()

    return matched, processed
