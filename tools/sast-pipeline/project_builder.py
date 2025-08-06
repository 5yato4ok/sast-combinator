import subprocess
import os


def build_environment(image_name="project-builder",
                      dockerfile_path="Dockerfiles/builder/Dockerfile",
                      project_path="/tmp/my_project",
                      output_dir="/tmp/sast_output",
                      config_path="config/analyzers.yaml",
                      force_rebuild=False):

    context_dir = os.path.abspath(".")  # assume this file is run from the root project
    os.makedirs(output_dir, exist_ok=True)

    print(f"[+] Building builder image: {image_name}")
    subprocess.run(
        ["docker", "build", "-t", image_name, "-f", dockerfile_path, "."],
        cwd=context_dir,  # use full project as build context
        check=True
    )


    print(f"[>] Running builder container...")
    container_name = f"{image_name}_container"
    subprocess.run([
        "docker", "run", "--rm",
        "--name", container_name,
        "-v", f"{os.path.abspath(project_path)}:/workspace",
        "-v", f"{os.path.abspath(output_dir)}:/shared/output",
        "-v", "/var/run/docker.sock:/var/run/docker.sock",  # For running child analyses containers
        "-e", f"FORCE_REBUILD={'1' if force_rebuild else '0'}",
        "-e", f"BUILDER_CONTAINER={container_name}",
        image_name
    ], check=True)

    print("[✓] Builder + analysis finished.")
