from __future__ import annotations
import os
from pathlib import Path
from urllib.parse import urlparse, unquote

import requests

AIST_TOKEN = os.environ.get("AIST_TOKEN")
ALLOWED_FILE_ROOTS: list[str] = [
    r for r in os.environ.get("ALLOWED_FILE_ROOTS", "").split(":") if r
]


def _validate_file_path(path: Path) -> Path:
    """Resolve and validate a file:// path against allowed roots."""
    resolved = path.resolve()
    if not ALLOWED_FILE_ROOTS:
        return resolved
    for root in ALLOWED_FILE_ROOTS:
        root_resolved = Path(root).resolve()
        if resolved == root_resolved or root_resolved in resolved.parents:
            return resolved
    raise ValueError(
        f"File path {resolved} is outside allowed roots: {ALLOWED_FILE_ROOTS}"
    )


def load_source_from_url(
    url: str,
    *,
    timeout: float = 15.0,
    max_bytes: int = 50 * 1024 * 1024,
) -> str:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        path = _validate_file_path(Path(unquote(parsed.path)))
        return path.read_text(encoding="utf-8", errors="replace")
    if parsed.scheme in {"http", "https"}:
        headers: dict[str, str] = {}
        if "/aist/" in url and AIST_TOKEN:
            headers = {
                "content-type": "application/json",
                "Authorization": f"Token {AIST_TOKEN}",
            }
        with requests.get(url, headers=headers, stream=True, timeout=timeout, verify=True) as r:
            r.raise_for_status()
            buf = bytearray()
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    if len(buf) + len(chunk) > max_bytes:
                        raise ValueError(f"Response exceeds max_bytes={max_bytes} limit")
                    buf.extend(chunk)
        return bytes(buf).decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported URL scheme for source loading: {parsed.scheme}")
