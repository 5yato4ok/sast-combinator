"""Observe actual Docker limits and deny a real write through the builder's runtime mount."""

import errno
import json
import os
import subprocess
from pathlib import Path

for runtime in json.loads(os.environ["SAST_BUILD_RUNTIMES"]):
    try:
        Path(runtime["root"], "write-probe").touch()
    except OSError as exc:
        if exc.errno != errno.EROFS:
            raise
    else:
        raise AssertionError("Builder can write to the analyzer runtime")
inspection = json.loads(subprocess.check_output(["docker", "inspect", os.environ["BUILDER_CONTAINER"]], text=True))[0]
Path("/shared/output/builder-check.json").write_text(json.dumps({
    "memory": inspection["HostConfig"]["Memory"],
    "cpus": inspection["HostConfig"]["NanoCpus"],
    "scratch": next(mount for mount in inspection["Mounts"] if mount["Destination"] == "/shared/build"),
}))
