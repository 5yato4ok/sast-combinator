"""
Entry point for running the SAST pipeline and optionally uploading the
generated reports to DefectDojo.

This script builds the project environment using ``project_builder`` and
executes each configured analyzer inside the builder container. Once the
analysis completes, it can upload the resulting reports into a specified
DefectDojo product. The product identifier is provided via a command‑line
argument.

Example usage:

```bash
python3 run_pipeline.py \
    --script path/to/build_config.sh \
    --output_dir /tmp/sast_output \
    --dojo_product_id 12
```

Environment variables required by analyzers (e.g. SNYK_TOKEN, SEMGREP_APP_TOKEN)
should be set in the environment or in a `.env` file in the current working
directory. The ``dotenv`` module is used to load variables from `.env`.
"""

from analyzer_runner import run_selected_analyzers
import os
import argparse
from dotenv import load_dotenv
from project_builder import configure_project_run_analyses
from defectdojo_api import upload_results

load_dotenv(dotenv_path=".env")

# run analyzators
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build and analyze a project using configured analyzers, "
                    "and optionally upload reports to DefectDojo."
    )
    parser.add_argument(
        "--script",
        required=True,
        help="Path to the script that configures the project for analysis."
    )
    parser.add_argument(
        "--output_dir",
        required=True,
        help="Directory on the host where analyzer results will be written."
    )
    parser.add_argument(
        "--project_version",
        required=False,
        default=None,
        help="Commit hash or branch on which to perform analysis. If omitted, the latest version is used."
    )
    parser.add_argument(
        "--project_force_rebuild",
        required=False,
        nargs='?',
        default=False,
        const=True,
        help="Force a fresh rebuild of the project. If provided without a value, it is treated as true."
    )
    parser.add_argument(
        "--dojo_product_name",
        required=False,
        help="If provided, upload resulting reports to the specified DefectDojo product after analysis."
    )
    parser.add_argument(
        "--dojo_config",
        required=False,
        default="config/defectdojo.yaml",
        help="Path to the DefectDojo configuration YAML. Defaults to config/defectdojo.yaml."
    )

    args = parser.parse_args()
    results_path = configure_project_run_analyses(args.script, args.output_dir,
                                                  force_rebuild=args.project_force_rebuild,
                                                  version=args.project_version)

    # Optionally upload scan results to DefectDojo
    if args.dojo_product_name:
        print(f"[=] Uploading reports to DefectDojo product {args.dojo_product_name}...")
        results = upload_results(
            output_dir=results_path,
            analyzers_cfg_path="config/analyzers.yaml",
            product_name=args.dojo_product_name,
            dojo_config_path=args.dojo_config,
        )
        print("[✓] DefectDojo upload complete.")
        # Optionally pretty print responses
        for analyzer_name, resp in results.items():
            print(f"    {analyzer_name}: {resp}")
    else:
        print("[!] No DefectDojo product ID provided. Skipping upload.")


# send to defect dojo to get results from it
