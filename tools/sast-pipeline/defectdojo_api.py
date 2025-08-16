"""
Helper functions for uploading static analysis results to DefectDojo via the
v2 REST API.

This module encapsulates loading DefectDojo connection settings from a YAML
configuration file, mapping custom analyzer output types to DefectDojo scan
types, and performing the import of reports for a given product.

Usage example:

>>> from defectdojo_api import upload_results
>>> upload_results(
...     output_dir="/tmp/sast_output",
...     analyzers_cfg_path="config/analyzers.yaml",
...     product_name="Test_suite",
...     dojo_config_path="config/defectdojo.yaml",
... )

The analyzers configuration must specify an `output_type` for each analyzer
(e.g. ``sarif`` or ``codechecker``). The file names of reports are
constructed as ``{analyzer_name}_result.{ext}``, where the extension is
derived from the output type (``.sarif`` for SARIF and ``.json`` for
CodeChecker unified JSON). If a report file is missing, a warning is
printed and that analyzer's report is skipped.

While this implementation uses the raw HTTP API directly via ``requests``,
it can be swapped out for any other DefectDojo client library if available.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import logging
from typing import Dict, Any, Optional

import yaml  # type: ignore
import requests

log = logging.getLogger(__name__)

def load_dojo_config(path: str) -> Dict[str, Any]:
    """Load DefectDojo connection settings from a YAML file.

    The YAML file must have a top-level ``defectdojo`` section with at least
    ``url`` and ``token``. Optionally, ``verify_ssl`` can be provided to
    disable SSL certificate verification.

    :param path: Path to the YAML configuration file.
    :return: A dictionary with keys ``url``, ``token`` and optionally
             ``verify_ssl``.
    :raises FileNotFoundError: if the file does not exist.
    :raises KeyError: if required keys are missing.
    """
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"DefectDojo config not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if "defectdojo" not in cfg:
        raise KeyError(f"Expected top‑level 'defectdojo' key in {config_path}")
    dojo_cfg = cfg["defectdojo"]
    if "url" not in dojo_cfg:
        raise KeyError(f"Missing 'url' in defectdojo config: {config_path}")
    return dojo_cfg


def resolve_scan_type(output_type: str) -> str:
    """Map an analyzer output_type to the appropriate DefectDojo scan_type.

    The mapping is defined here centrally. If additional formats are added
    in analyzers.yaml, extend this mapping accordingly.

    :param output_type: The lower‑case output format defined for the analyzer.
    :return: A string accepted by DefectDojo's ``import-scan`` API as
             ``scan_type``.
    :raises ValueError: if the output_type is unknown.
    """
    mapping = {
        "sarif": "SARIF",
        "codechecker": "Codechecker Report native",
    }
    key = (output_type or "").strip().lower()
    if key not in mapping:
        supported = ", ".join(sorted(mapping.keys()))
        raise ValueError(f"Unknown output_type '{output_type}'. Supported: {supported}")
    return mapping[key]


def upload_report(
    analyzer_name,
    dojo_cfg: Dict,
    dojo_token: str,
    product_name: str,
    scan_type: str,
    report_path: str
) -> Dict[str, Any]:
    """Upload a single report file to DefectDojo.

    :param dojo_cfg: Dict, containing configuration for Defect Dojo
    :param dojo_token: API token for authentication.
    :param product_name: ID of the product (project) to attach the scan to.
    :param scan_type: Type of scan, as understood by DefectDojo.
    :param report_path: Path to the report file on disk.
    :return: Parsed JSON response from DefectDojo.
    :raises Exception: if the HTTP request fails or returns a non‑2xx status.
    """
    dojo_url = dojo_cfg.get("url")
    api_endpoint = "/api/v2/import-scan/"
    full_url = dojo_url.rstrip("/") + api_endpoint
    headers = {"Authorization": f"Token {dojo_token}"}
    data = {
        "scan_type": scan_type,
        "product_name": str(product_name),
        "active": "true",
        "verified": "true",
        "engagement_name": analyzer_name,
        "minimum_severity": dojo_cfg.get("minimum_severity", "Info"),
        "auto_create_context" : dojo_cfg.get("auto_create_context", "true")
    }
    file_name = os.path.basename(report_path)
    with open(report_path, "rb") as f:
        files = {"file": (file_name, f)}
        response = requests.post(
            full_url,
            headers=headers,
            data=data,
            files=files,
            verify=dojo_cfg.get("verify_ssl", True),
            #timeout=120,
        )
    if response.status_code >= 400:
        try:
            err_msg = response.json()
        except Exception:
            err_msg = response.text
        raise Exception(
            f"DefectDojo upload failed with status {response.status_code}: {err_msg}"
        )
    try:
        return response.json()
    except Exception:
        return {"status_code": response.status_code, "text": response.text}


def upload_results(
    output_dir: str,
    analyzers_cfg_path: str,
    product_name: str | int,
    dojo_config_path: str,
) -> Dict[str, Any]:
    """Upload all analyzer reports from a directory into DefectDojo.

    This function reads the analyzers configuration to determine which
    analyzers were run, their output types, and therefore the expected file
    names for their reports. For each enabled analyzer, it looks for a
    report file in ``output_dir`` named ``{analyzer_name}_result.{ext}`` where
    the extension is ``sarif`` for SARIF output types and ``json`` for
    CodeChecker output. Missing files are skipped with a warning. Successful
    uploads are collected into a dictionary keyed by analyzer name.

    :param output_dir: Directory containing the analyzer result files.
    :param analyzers_cfg_path: Path to the analyzers YAML file.
    :param product_name: DefectDojo product/project identifier.
    :param dojo_config_path: Path to the DefectDojo connection YAML.
    :return: A mapping of analyzer names to upload responses.
    """
    dojo_cfg = load_dojo_config(dojo_config_path)

    dojo_token = os.environ.get("DEFECT_DOJO_TOKEN", None)
    if dojo_token is None:
        raise Exception("Environmental variable DEFECT_DOJO_TOKEN is not set up")

    # Load analyzers configuration
    analyzers_path = Path(analyzers_cfg_path).expanduser().resolve()
    with analyzers_path.open("r", encoding="utf-8") as f:
        analyzers_config = yaml.safe_load(f) or {}
    analyzers_list = analyzers_config.get("analyzers", [])

    results: Dict[str, Any] = {}
    for analyzer in analyzers_list:
        # Skip disabled analyzers
        if not analyzer.get("enabled", True):
            continue
        name = analyzer.get("name")
        output_type = analyzer.get("output_type", "sarif")
        try:
            scan_type = resolve_scan_type(output_type)
        except ValueError as e:
            log.warning(f"[ERROR] {e}. Skipping analyzer '{name}'.")
            continue
        ext = "sarif" if output_type.lower() == "sarif" else "json"
        report_file = os.path.join(output_dir, f"{name}_result.{ext}")
        if not os.path.isfile(report_file):
            log.warning(f"[ERROR] Report file not found for analyzer '{name}': {report_file}")
            continue
        try:
            log.info(f"Started to upload {name} report to DefectDojo")
            resp = upload_report(
                analyzer_name=name,
                dojo_cfg=dojo_cfg,
                dojo_token=dojo_token,
                product_name=product_name,
                scan_type=scan_type,
                report_path=report_file
            )
            results[name] = resp
            log.info(f"Uploaded {name} report to DefectDojo")
        except Exception as exc:
            log.warning(f"Failed to upload {name} report: {exc}")
    return results