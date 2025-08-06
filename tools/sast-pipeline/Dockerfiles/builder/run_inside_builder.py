from analyzer_runner import run_selected_analyzers

from pathlib import Path
import json
import os

if __name__ == "__main__":

    print("[*] Filtering compile_commands.json to first entry only (for test)...")

    cc_path = Path("/workspace/build-tmp/nx_open/build/compile_commands.json")
    if cc_path.exists():
        with cc_path.open() as f:
            data = json.load(f)

        filtered = data[:5]

        with cc_path.open("w") as f:
            json.dump(filtered, f, indent=2)

        print("[✓] compile_commands.json filtered.")
    else:
        print(f"[!] File not found: {cc_path}")

    print("[>] Running analyzer: codechecker...")

    run_selected_analyzers(
        config_path="/app/config/analyzers.yaml",
        analyzers_to_run=["codechecker"],
        exclude_slow=False,
        project_path="/workspace/build-tmp/nx_open",
        output_dir="/shared/output",
        builder_container = os.environ.get("BUILDER_CONTAINER", "builder-env")
    )
