"""
Enhanced entrypoint for running the SAST pipeline.

This version adds support for configurable logging and YAML based
configuration files.  If the ``--config`` option is provided, the
specified YAML file is loaded and used to populate or override
command‑line arguments.  The logging level can be controlled via
``--log-level`` (e.g. DEBUG, INFO, WARNING), and all messages are
emitted through Python's ``logging`` module rather than printed
directly.  This allows log messages to be filtered or redirected via
handlers, and keeps the pipeline output quiet unless debugging is
enabled.
"""

from __future__ import annotations

import argparse
import logging
import os
from dotenv import load_dotenv
from project_builder import configure_project_run_analyses
from defectdojo_api import upload_results
import yaml  # type: ignore

load_dotenv(dotenv_path=".env")

def load_config(path: str) -> dict:
    """Load a YAML configuration file if it exists.

    The configuration file may specify any of the command line
    arguments accepted by this script. Keys that match the argument
    names (e.g. ``script``, ``output_dir``, ``project_version``) will
    override the corresponding command line values.

    :param path: Path to the YAML configuration file.
    :return: Dict of configuration values, or an empty dict if the
             file could not be loaded.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {path}")
    except Exception as exc:
        raise RuntimeError(f"Failed to load configuration from {path}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build and analyse a project using configured analyzers, "
            "and optionally upload reports to DefectDojo."
        )
    )
    parser.add_argument(
        "--script",
        help=(
            "Path to the script that configures the project for analysis. "
            "This value may be overridden by a configuration file."
        ),
        required=False,
    )
    parser.add_argument(
        "--output_dir",
        help=(
            "Directory on the host where analyzer results will be written. "
            "May be overridden by a configuration file."
        ),
        required=False,
    )
    parser.add_argument(
        "--project_version",
        required=False,
        default=None,
        help=(
            "Commit hash or branch on which to perform analysis. If omitted, "
            "the latest version is used."
        ),
    )
    parser.add_argument(
        "--project_force_rebuild",
        required=False,
        nargs="?",
        default=False,
        const=True,
        help=(
            "Force a fresh rebuild of the project. If provided without a value, "
            "it is treated as true."
        ),
    )
    parser.add_argument(
        "--dojo_product_name",
        required=False,
        help=(
            "If provided, upload resulting reports to the specified DefectDojo "
            "product after analysis."
        ),
    )
    parser.add_argument(
        "--dojo_config",
        required=False,
        default="config/defectdojo.yaml",
        help="Path to the DefectDojo configuration YAML. Defaults to config/defectdojo.yaml.",
    )
    parser.add_argument(
        "--config",
        required=False,
        default=None,
        help=(
            "Path to a YAML file containing configuration values. The keys in "
            "this file correspond to command-line argument names (e.g. script, "
            "output_dir, dojo_product_name). Values in this file override "
            "values provided on the command line."
        ),
    )
    parser.add_argument(
        "--log-level",
        required=False,
        default="INFO",
        help="Logging level (e.g. DEBUG, INFO, WARNING, ERROR). Defaults to INFO.",
    )

    args = parser.parse_args()

    # Apply configuration file overrides
    if args.config:
        cfg = load_config(args.config)
        for key, value in cfg.items():
            if hasattr(args, key):
                setattr(args, key, value)

    # Configure logging
    level_name = (args.log_level or "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    log = logging.getLogger(__name__)

    # Validate required arguments after config merging
    if not args.script:
        parser.error("--script is required (either via CLI or config file)")
    if not args.output_dir:
        parser.error("--output_dir is required (either via CLI or config file)")

    # Build project and run analyses
    log.info("Building builder image and running analyzers…")

    results_path = configure_project_run_analyses(
        args.script,
        args.output_dir,
        force_rebuild=args.project_force_rebuild,
        version=args.project_version,
        log_level=args.log_level,
    )

    # Optionally upload results
    if args.dojo_product_name:
        log.info(
            "Uploading reports to DefectDojo product %s…", args.dojo_product_name
        )
        results = upload_results(
            output_dir=results_path,
            analyzers_cfg_path="config/analyzers.yaml",
            product_name=args.dojo_product_name,
            dojo_config_path=args.dojo_config,
        )
        log.info("DefectDojo upload complete.")
        for analyzer_name, resp in results.items():
            log.debug("%s: %s", analyzer_name, resp)
    else:
        log.info("No DefectDojo product specified. Skipping upload.")


if __name__ == "__main__":
    main()