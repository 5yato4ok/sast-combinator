from analyzer_runner import run_selected_analyzers
import os
from dotenv import load_dotenv
from project_builder import build_environment

load_dotenv(dotenv_path=".env")

# run analyzators
if __name__ == "__main__":
    force_rebuild = os.environ.get("FORCE_REBUILD", "0")
    build_environment(force_rebuild=(force_rebuild == "1"))


# send to defect dojo to get results from it
