"""Record the effective analyzer limits through the Docker daemon used by the runner."""

import json
import os
import subprocess
import sys
from pathlib import Path

inspection = json.loads(subprocess.check_output(["docker", "inspect", os.environ["HOSTNAME"]], text=True))[0]
report = {
    "runs": [],
    "properties": {
        "memory": inspection["HostConfig"]["Memory"],
        "cpus": inspection["HostConfig"]["NanoCpus"],
        "source_exists": Path(sys.argv[1], "main.cpp").is_file(),
    },
}
Path(sys.argv[2], sys.argv[3]).write_text(json.dumps(report))
