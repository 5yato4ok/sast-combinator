import subprocess
import os
import shutil
from pathlib import Path
from datetime import datetime


def image_exists(image_name: str) -> bool:
    result = subprocess.run(
        ["docker", "images", "-q", image_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True
    )
    return result.stdout.strip() != ""


def configure_project_run_analyses(script_path,
                                   output_dir,
                                   image_name="project-builder",
                                   dockerfile_path="Dockerfiles/builder/Dockerfile",
                                   project_path="/tmp/my_project",
                                   force_rebuild=False,
                                   version=None):

    context_dir = os.path.abspath(".")  # assume this file is run from the root project

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"{output_dir}/{timestamp}"
    os.makedirs(output_dir, exist_ok=True)

    print(f"[+] Building builder image: {image_name}")

    if image_exists(image_name):
        subprocess.run(
            ["docker", "image", "rm", image_name],
            check=True,
            text=True
        )

    input_path = Path(script_path).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    context_path = Path(context_dir).resolve()
    target_dir = context_path / "tmp"

    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy file
    target_path = target_dir / input_path.name
    shutil.copy2(input_path, target_path)

    relative_config_path = target_path.relative_to(context_path)

    subprocess.run(
        ["docker", "build", "--build-arg", f"PROJECT_CONFIG_PATH={str(relative_config_path)}", "-t", image_name, "-f",
         dockerfile_path, "."],
        cwd=context_dir,  # use full project as build context
        check=True,
        text=True
    )

    # Cleanup after build — here simulated directly
    # If you want to delete it after actual Docker build, move this to another script
    try:
        target_path.unlink()
        # Optionally remove the subdirectory if empty
        if not any(target_dir.iterdir()):
            target_dir.rmdir()
    except Exception as e:
        print(f"[!] Warning: Failed to delete copied file: {e}")

    print(f"[>] Running builder container...")
    container_name = f"{image_name}_container"

    env_args = [
        "-e", f"FORCE_REBUILD={'1' if force_rebuild else '0'}",
        "-e", f"BUILDER_CONTAINER={container_name}",
    ]

    if version is not None:
        env_args += ["-e", f"PROJECT_VERSION={str(version)}"]

    subprocess.run([
        "docker", "run", "--rm",
        "--name", container_name,
        "-v", f"{os.path.abspath(project_path)}:/workspace",
        "-v", f"{os.path.abspath(output_dir)}:/shared/output",
        "-v", "/var/run/docker.sock:/var/run/docker.sock",  # For running child analyses containers
        *env_args,
        image_name
    ], check=True, text=True)

    print("[✓] Builder + analysis finished.")
