"""Where one pipeline run puts its results, and how it writes them there.

Every execution type produces results the same way -- one timestamped directory per run,
JSON handoffs replaced atomically -- so that contract lives here rather than inside any one
producer. Owning it in ``project_builder`` made the SAST builder the de-facto owner of a
package-wide rule and forced the DAST executor to import the whole builder (and its Docker
and agent-bridge dependencies) to reach two small functions.

This module imports nothing from the package on purpose: it is a leaf every producer can
depend on, including the ones that ship inside a minimal container image.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


def prepare_run_output_dir(output_dir: str | Path) -> Path:
    """Create the timestamped directory shared by every pipeline result producer."""
    run_output_dir = Path(output_dir) / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_output_dir.mkdir(exist_ok=True, parents=True)
    return run_output_dir


def write_json_atomically(output_dir: Path, filename: str, payload: dict[str, Any]) -> Path:
    """Durably replace one JSON handoff without exposing a partially written file."""
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_dir,
            prefix=f".{filename}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, sort_keys=True, separators=(",", ":"))
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.chmod(0o600)
        final_path = output_dir / filename
        temporary_path.replace(final_path)
        return final_path
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
