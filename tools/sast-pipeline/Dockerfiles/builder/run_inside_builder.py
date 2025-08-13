from analyzer_runner import run_selected_analyzers
from dotenv import load_dotenv

from pathlib import Path
import json
import os

load_dotenv(dotenv_path="/app/.env")

if __name__ == "__main__":
    #
    # print("[*] Filtering compile_commands.json to first entry only (for test)...")
    #
    # cc_path = Path("/workspace/build-tmp/nx_open/build/compile_commands.json")
    # if cc_path.exists():
    #     with cc_path.open() as f:
    #         data = json.load(f)
    #
    #     filtered = data[:5]
    #
    #     with cc_path.open("w") as f:
    #         json.dump(filtered, f, indent=2)
    #
    #     print("[✓] compile_commands.json filtered.")
    # else:
    #     print(f"[!] File not found: {cc_path}")

    print("[>] Running analyzer...")

    builder_container = os.environ.get("BUILDER_CONTAINER", None)
    if builder_container is None:
        raise Exception("Enviromental variabl BUILDER_CONTAINER is not set. Terminating.")

    project_path = os.environ.get("PROJECT_PATH", None)
    if project_path is None:
        raise Exception("Enviromental variabl PROJECT_PATH is not set. Terminating.")

    run_selected_analyzers(
        config_path="/app/config/analyzers.yaml",
        exclude_slow=False,
        project_path=project_path,
        output_dir="/shared/output",
        builder_container = builder_container,
        analyzers_to_run=["codechecker"]
    )
