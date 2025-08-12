from analyzer_runner import run_selected_analyzers
import os
import argparse
from dotenv import load_dotenv
from project_builder import configure_project_run_analyses

load_dotenv(dotenv_path=".env")

# run analyzators
if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Analyze project with number of analyzators"
    )
    parser.add_argument(
        "--script", required=True,
        help="Path to the script, which configures project for future analyses"
    )
    parser.add_argument(
        "--output_dir", required=True,
        help="Path to directory, where results should be stored"
    )
    parser.add_argument(
        "--project_version", required=False, default=None,
        help="Commit hash/Branch of project, on which analyze should be performed. By default latest version will be used"
    )
    parser.add_argument(
        "--project_force_rebuild",  required=False, nargs='?', default=False,  const=True,
        help="Should project be rebuild from zero"
    )

    args = parser.parse_args()
    configure_project_run_analyses(args.script, args.output_dir, force_rebuild=args.project_force_rebuild,
                                   version=args.project_version)


# send to defect dojo to get results from it
