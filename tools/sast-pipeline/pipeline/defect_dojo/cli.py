from dotenv import load_dotenv
import argparse
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=getattr(logging, "INFO", logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)

if __package__ in (None, ""):
    import os, sys
    # add project root (folder that contains "pipeline/")
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from pipeline.defect_dojo.utils import (
    upload_results,
    delete_findings_by_product_and_path_prefix,
)

load_dotenv(dotenv_path="../.env")
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
        default="../config/defectdojo.yaml",
        help="Path to the DefectDojo configuration YAML. Defaults to config/defectdojo.yaml.",
    )

    parser.add_argument(
        "--repo_path",
        required=True,
        help="Path to downloaded repository. Usually locates in /tmp/my_project/build-tmp/{project_name}",
    )

    parser.add_argument(
        "--trim_path",
        required=True,
        help="Path to trim from finding",
    )

    parser.add_argument(
        "--log_level",
        required=False,
        help="Path to trim from finding",
    )

    args = parser.parse_args()
    level_name = (args.log_level or "INFO").upper()
    logger.setLevel(level_name)

    upload_results(args.results_path, '../config/analyzers.yaml', args.dojo_product_name, '../config/defectdojo.yaml',
                   args.repo_path, args.trim_path)