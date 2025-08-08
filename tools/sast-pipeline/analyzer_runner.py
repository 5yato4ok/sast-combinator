import subprocess
import yaml
import os
from pathlib import Path

ANALYZER_ORDER = {
    "fast": 0,
    "medium": 1,
    "slow": 2
}

def image_exists(image_name: str) -> bool:
    result = subprocess.run(
        ["docker", "images", "-q", image_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True
    )
    return result.stdout.strip() != ""

def build_image_if_needed(image_name: str, dockerfile_dir: str):
    if image_exists(image_name):
        print(f"[=] Image '{image_name}' already exists.")
        return
    print(f"[+] Building image '{image_name}'...")
    subprocess.run(
        ["docker", "build", "-t", image_name, "."],
        cwd=dockerfile_dir,
        text=True,
        check=True
    )


def run_docker(image: str, builder_container: str, args: list, project_path: str, output_dir: str,
               env_vars: list = None):
    print(f"[>] Running analyzer: {image}")

    cmd = [
        "docker", "run", "--rm",
        #"-v", f"{project_path}:/workspace",         # project source
        "--volumes-from", builder_container,
        #"-v", f"{output_dir}:/shared/output"  # result output
    ]

    if env_vars:
        for var in env_vars:
            if var in os.environ:
                cmd += ["-e", f"{var}={os.environ[var]}"]
            else:
                raise Exception(f"[!] Warning: Environment variable '{var}' is not set.")

    cmd += [image] + args

    subprocess.run(cmd, check=True, text=True)


def run_selected_analyzers(
    config_path: str,
    analyzers_to_run: list = None,
    exclude_slow: bool = False,
    project_path: str = "./my_project",
    output_dir: str = "/tmp/sast_output",
    builder_container: str = "builder-env"
):
    # Ensure output dir exists
    os.makedirs(output_dir, exist_ok=True)

    # Load analyzers config
    with open(config_path) as f:
        config = yaml.safe_load(f)

    analyzers = config["analyzers"]

    if analyzers_to_run:
        analyzers = [a for a in analyzers if a["name"] in analyzers_to_run]

    analyzers.sort(key=lambda a: ANALYZER_ORDER.get(a.get("time_class", "medium"), 1))

    for analyzer in analyzers:
        name = analyzer["name"]
        image = analyzer["image"]
        time_class = analyzer.get("time_class", "medium")
        dockerfile_path = f"/app/Dockerfiles/{name}"

        if exclude_slow and time_class == "slow":
            print(f"[!] Skipping '{name}' (marked as slow)")
            continue

        build_image_if_needed(image, dockerfile_path)

        input_path = analyzer.get("input", project_path)
        args = [input_path, "/shared/output"]

        env_vars = analyzer.get("env", [])
        run_docker(image, builder_container, args, project_path, output_dir, env_vars)

    print("[✓] All selected analyzers completed.")
