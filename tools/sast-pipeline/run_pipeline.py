from run_analyzers import run_selected_analyzers
from dotenv import load_dotenv

# Clones the repo or checks the existing repo, updates if required
#
# Runs the project build script which:
#
# Installs deps (e.g., via Conan).
#
# Generates compile_commands.json.
#
# All in an isolated workspace dir, e.g.Docker

load_dotenv(dotenv_path=".env")

# run analyzators
if __name__ == "__main__":
    run_selected_analyzers(
        config_path="config/analyzers.yaml",
        project_path="/Users/butkevichveronika/work/nx_open",        # исходники
        output_dir="/Users/butkevichveronika/work/sast-combinators-results",           # папка с результатами
        analyzers_to_run=["snyk"],                    # или список ["cppcheck", "devskim"]
        exclude_slow=False
    )



# send to defect dojo to get results from it
