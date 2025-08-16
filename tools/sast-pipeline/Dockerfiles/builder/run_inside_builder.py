from analyzer_runner import run_selected_analyzers
from dotenv import load_dotenv
import logging

from pathlib import Path
import json
import os

load_dotenv(dotenv_path="/app/.env")
log = logging.getLogger(__name__)

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL"), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)

if __name__ == "__main__":
    cc_path = Path("/workspace/build-tmp/nx_open/build/compile_commands.json")
    if cc_path.exists():
        with cc_path.open() as f:
            data = json.load(f)

        filtered = data[:10]

        with cc_path.open("w") as f:
            json.dump(filtered, f, indent=2)

        log.info("[INFO] compile_commands.json filtered.")
    else:
        log.info(f"[ERROR] File not found: {cc_path}")

    builder_container = os.environ.get("BUILDER_CONTAINER")
    if not builder_container:
        raise EnvironmentError(
            "Environmental variable BUILDER_CONTAINER is not set. Terminating."
        )
    project_path = os.environ.get("PROJECT_PATH")
    if not project_path:
        raise EnvironmentError(
            "Environmental variable PROJECT_PATH is not set. Terminating."
        )

    log.info("Starting analyzer runner...")

    run_selected_analyzers(
        config_path="/app/config/analyzers.yaml",
        exclude_slow=False,
        project_path=project_path,
        output_dir="/shared/output",
        analyzers_to_run=["bearer"],
        builder_container = builder_container,
        log_level = os.environ.get("LOG_LEVEL", None)
    )
