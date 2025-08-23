from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import requests

from .client import DefectDojoClient, DojoConfig, ImportResult

logger = logging.getLogger(__name__)


class LinkBuilder:
    """Build source links for GitHub/GitLab/Bitbucket; verify remote file existence (handles 429)."""

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

    @staticmethod
    def remote_link_exists(url: str, timeout: int = 5, max_retries: int = 3) -> Optional[bool]:
        """Return True if GET 200/3xx, False if 404, None for other errors. Retries on 429."""
        try:
            r = requests.get(url, allow_redirects=True, timeout=timeout)
            logger.debug(f"Checking url {url}. Status code {r.status_code}")
            if r.status_code == 429 and max_retries > 0:
                retry = int(r.headers.get("Retry-After", "1"))
                logger.warning(f"Too many requests to github. Sleep for {retry}")
                import time
                time.sleep(retry)
                return LinkBuilder.remote_link_exists(url, timeout, max_retries - 1)
            if r.status_code == 200:
                return True
            if 300 <= r.status_code < 400:
                return True
            if r.status_code == 404:
                logger.warning(f"Url is not valid repo file: {url}")
                return False
            logger.warning(f"Unknown return code {r.status_code}")
            return None
        except requests.RequestException:
            return None


class SastPipelineDDClient(DefectDojoClient):
    """Extensions that implement original SAST pipeline behavior (import, trim, enrich)."""

    @staticmethod
    def derive_engagement_name(analyzer_name: str, branch: Optional[str], commit: Optional[str], name_mode: str) -> str:
        short = (commit or "")[:8] if commit else None
        if name_mode == "analyzer":
            return analyzer_name
        if name_mode == "analyzer-branch":
            return "-".join([x for x in [analyzer_name, branch] if x])
        return "-".join([x for x in [analyzer_name, short] if x]) or analyzer_name

    # Upload single report: import -> collect findings -> trim -> enrich
    def upload_report(self,
                      analyzer_name: str,
                      product_name: str,
                      scan_type: str,
                      report_path: str,
                      repo_params,
                      trim_path: str) -> ImportResult:
        if not os.path.isfile(report_path):
            raise FileNotFoundError(f"Report path does not exist: {report_path}")

        product = self.get_or_create_product(product_name)

        engagement_name = self.derive_engagement_name(analyzer_name, repo_params.branch_tag, repo_params.commit_hash, self.cfg.name_mode)
        engagement = self.ensure_engagement(
            product_id=product["id"],
            name=engagement_name,
            repo_url=repo_params.repo_url,
            branch_tag=repo_params.branch_tag,
            commit_hash=repo_params.commit_hash,
            engagement_status=self.cfg.engagement_status,
        )
        logger.info("Using engagement '%s' (id=%s)", engagement_name, engagement["id"])

        # Import
        import_resp = self.import_scan(
            engagement_id=int(engagement["id"]),
            scan_type=scan_type,
            report_path=report_path,
            minimum_severity=self.cfg.minimum_severity,
            build_id=repo_params.commit_hash or None,
        )
        logger.info("Import finished for %s", analyzer_name)

        # Collect findings
        findings: List[Dict[str, Any]] = []
        test_id: Optional[int] = None
        if isinstance(import_resp, dict):
            if "test" in import_resp and import_resp.get("test"):
                test_id = import_resp["test"]["id"] if isinstance(import_resp["test"], dict) else import_resp["test"]
                findings = self.get_findings_for_test(int(test_id))
            elif "findings" in import_resp and isinstance(import_resp["findings"], list):
                ids = [fi.get("id") if isinstance(fi, dict) else fi for fi in import_resp["findings"]]
                for fid in ids:
                    findings.append(self.get_finding(int(fid)))

        imported_count = len(findings)

        # Enrich metadata (trim + link)
        linker = LinkBuilder()
        ref = repo_params.commit_hash or repo_params.branch_tag
        logger.info(f"Start enriching {len(findings)} findings")

        def _validate_and_update_finding(finding: Dict[str, Any]) -> Dict[str, Any]:
            file_path = finding.get("file_path", "")
            if not trim_path:
                return finding
            # Only if path starts with trim_path; ensure slash handling matches original
            if not file_path.startswith(trim_path):
                return finding
            tp = trim_path if trim_path.endswith("/") else trim_path + "/"
            finding["file_path"] = file_path.replace(tp, "")
            return self.patch_finding(finding)

        def _process_one(f) -> int:
            try:
                # trim patch if needed
                f = _validate_and_update_finding(f)
                file_path = f.get("file_path", "")
                link = linker.build(repo_params.repo_url or "", file_path, ref)
                if not link:
                    return 0

                exists = linker.remote_link_exists(link)
                # Only delete when we are sure link is invalid (404)
                if exists is True:
                    self.post_finding_meta_json(f["id"], "sourcefile_link", link)
                    return 1
                elif exists is False:
                    logger.warning("Deleting %s", f.get("id"))
                    self.delete_finding(f["id"])
                    return 0
                else:
                    # Unknown / transient condition -> do nothing, don't delete
                    logger.warning("Skip enrichment for %s due to ambiguous link check: %s", f.get("id"), link)
                    return 0
            except Exception as e:
                logger.warning("Failed to enrich finding %s: %s", f.get("id"), e)
                return 0

        enriched = 0
        workers = max(1, (os.cpu_count() or 4))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_process_one, f) for f in findings]
            for fut in as_completed(futures):
                enriched += fut.result()
                if enriched and enriched % 100 == 0:
                    logger.info("Enriched %d findings on this page", enriched)

        logger.info("Enriched findings: %s/%s", enriched, imported_count)
        return ImportResult(
            engagement_id=int(engagement["id"]),
            engagement_name=engagement_name,
            test_id=int(test_id) if test_id else None,
            imported_findings=imported_count,
            enriched_count=enriched,
            raw=import_resp,
        )

    # Bulk enrichment across product (keeps original behavior)
    def enrich_existing(self, product_name: Optional[str], only_missing: bool = True, max_workers: Optional[int] = None) -> int:

        params: Dict[str, Any] = {"related_fields": "true", "limit": 200}
        if product_name:
            params["product_name"] = product_name

        linker = LinkBuilder()
        updated_total = 0
        offset = 0

        eng_cache = {}
        eng_cache_lock = threading.Lock()
        if max_workers is None:
            max_workers = max(1, (os.cpu_count() or 4))

        def _process_one_finding(f: dict) -> int:
            try:
                fid = f.get("id")
                file_path = f.get("file_path") or ""
                if not fid or not file_path:
                    return 0

                # Resolve engagement: prefer embedded, else fetch by id with cache
                eng = None
                test = f.get("test") or {}
                eng_obj = test.get("engagement")
                if isinstance(eng_obj, dict):
                    eng = eng_obj
                elif isinstance(eng_obj, int):
                    eng = self.fetch_engagement(eng_obj, eng_cache, eng_cache_lock)

                if eng is None and isinstance(f.get("engagement"), dict):
                    eng = f.get("engagement")

                if not isinstance(eng, dict):
                    return 0

                repo_url = eng.get("source_code_management_uri")
                ref = eng.get("commit_hash") or eng.get("branch_tag")
                if not repo_url:
                    return 0

                if only_missing and self.has_sourcefile_link(int(fid)):
                    return 0

                link = linker.build(repo_url, file_path, ref)
                if not link:
                    return 0

                self.post_finding_meta_json(int(fid), "sourcefile_link", link)
                return 1
            except Exception as e:
                logger.warning("Failed to enrich finding id=%s: %s", f.get("id"), e)
                return 0

        while True:
            page_params = dict(params, offset=offset)
            j = self.list_findings(**page_params)
            findings = j.get("results", [])
            if not findings:
                break

            processed_on_page = 0
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = [ex.submit(_process_one_finding, f) for f in findings]
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
