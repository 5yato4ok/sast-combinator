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
from pipeline.project_builder import configure_project_run_analyses
from pipeline.defectdojo_api import upload_results
import yaml  # type: ignore
import pipeline.config_utils as config_utils

log = logging.getLogger(__name__)

load_dotenv(dotenv_path="pipeline/.env")
ANALYZERS_CONFIG = config_utils.AnalyzersConfigHelper(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline" , "config", "analyzers.yaml"))

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

def cleanup(analyzer_config_path):
    log.info(f"Trying to delete file {analyzer_config_path}")

    if os.path.exists(analyzer_config_path):
        os.remove(analyzer_config_path)

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
        "--product_name",
        required=False,
        help=(
            "Name of product, which will be used for image name. Can be skipped if dojo_product_name is provided"
        ),
    )
    parser.add_argument(
        "--dojo_config",
        required=False,
        default=os.path.join(CURRENT_DIR, "pipeline", "config", "defectdojo.yaml"),
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
        "--log_level",
        required=False,
        default="INFO",
        help="Logging level (e.g. DEBUG, INFO, WARNING, ERROR). Defaults to INFO.",
    )
    parser.add_argument(
        "--languages",
        required=False,
        nargs="+",
        choices=ANALYZERS_CONFIG.get_supported_languages(),
        help="Select languages to filter used analyzers. Can select one or several supported choices",
    )

    parser.add_argument(
        "--time_class_level",
        required=False,
        default=False,
        choices=ANALYZERS_CONFIG.get_analyzers_time_class(),
        help="Analyzers time class level.",
    )

    parser.add_argument(
        "--analyzers",
        required=False,
        nargs="+",
        default=[],
        choices=ANALYZERS_CONFIG.get_supported_analyzers(),
        help="Select used analyzers. Note: if the analyzer doesn't support provided language it will be excluded.",
    )

    parser.add_argument(
        "--rebuild_images",
        required=False,
        nargs="?",
        default=False,
        const=True,
        help=(
            "Force a fresh rebuild of the analyzers and builder images"
        ),
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
    log = logging.getLogger(__name__) # TODO: check if requires to rewrite

    # Validate required arguments after config merging
    if not args.script:
        parser.error("--script is required (either via CLI or config file)")
    if not args.output_dir:
        parser.error("--output_dir is required (either via CLI or config file)")
    if not args.languages:
        parser.error("--languages is required (either via CLI or config file)")

    if not args.dojo_product_name and not args.product_name:
        parser.error("--dojo_product_name or --project_name  required (either via CLI or config file)")

    # Build project and run analyses
    log.info("Building builder image and running analyzers…")

    if args.dojo_product_name:
        project_name = args.dojo_product_name
    else:
        project_name =args.product_name

    launch_description = configure_project_run_analyses(
        args.script,
        args.output_dir,
        languages=args.languages,
        analyzer_config=ANALYZERS_CONFIG,
        force_rebuild=args.project_force_rebuild,
        version=args.project_version,
        log_level=level_name,
        min_time_class = args.time_class_level,
        analyzers=args.analyzers,
        image_name=f"project_{project_name.lower()}_builder",
        rebuild_images=args.rebuild_images,
        dockerfile_path=os.path.join(CURRENT_DIR, "Dockerfiles", "builder", "Dockerfile"),
        context_dir=CURRENT_DIR
    )

    if not launch_description or not launch_description.get("is_correct", False):
        log.info("No analyzers were launched. Exit.")
        return
    print(launch_description)
    # Optionally upload results
    if args.dojo_product_name:
        log.info(
            "Uploading reports to DefectDojo product %s…", args.dojo_product_name
        )
        results = upload_results(
            output_dir=launch_description["output_dir"],
            analyzers_cfg_path=launch_description["tmp_analyzer_config_path"],
            product_name=args.dojo_product_name,
            dojo_config_path=args.dojo_config,
            repo_path=launch_description["project_path"],
            trim_path=launch_description["trim_path"]
        )
        log.info("DefectDojo upload complete.")
        for result in results:
            log.debug("%s: imported findings %d", result.engagement_name, result.imported_findings)
    else:
        log.info("No DefectDojo product specified. Skipping upload.")

    cleanup(launch_description["tmp_analyzer_config_path"])


if __name__ == "__main__":
    main()