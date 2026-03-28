import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mcp_server
from context_extractor.project_analysis import find_route_to_function, trace_identifier_backward

__all__ = [
    "TemporaryDirectory",
    "Path",
    "find_route_to_function",
    "mcp_server",
    "trace_identifier_backward",
    "_stub_read_source",
]


def _stub_read_source(source: str, file_name: str):
    def _reader(_pipeline_id: str, _file_path: str):
        return source, Path(file_name)

    return _reader
