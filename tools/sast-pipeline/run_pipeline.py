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

    args = parser.parse_args()
    force_rebuild = os.environ.get("FORCE_REBUILD", "0")
    configure_project_run_analyses(args.script, force_rebuild=(force_rebuild == "1"),)


# send to defect dojo to get results from it
