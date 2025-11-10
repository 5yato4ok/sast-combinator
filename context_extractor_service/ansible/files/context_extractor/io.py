from __future__ import annotations
import os
from pathlib import Path
from urllib.parse import urlparse, unquote
import requests

AIST_TOKEN = os.environ.get("AIST_TOKEN", "secret-token")

def load_source_from_url(
    url: str,
    *,
    timeout: float = 15.0,
    max_bytes: int = 50 * 1024 * 1024,
) -> str:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        path = Path(unquote(parsed.path))
        return path.read_text(encoding="utf-8", errors="replace")
    if parsed.scheme in {"http", "https"}:
        headers = {}
        if "/aist/" in url:
            headers = {
                "content-type": "application/json",
                "Authorization": f"Token {AIST_TOKEN}",
            }
        # TODO: return verify=True
        with requests.get(url, headers=headers, stream=True, timeout=timeout, verify=False) as r:
            r.raise_for_status()
            buf = bytearray()
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    if len(buf) + len(chunk) > max_bytes:
                        raise ValueError(f"Response exceeds max_bytes={max_bytes} limit")
                    buf.extend(chunk)
        return bytes(buf).decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported URL scheme for source loading: {parsed.scheme}")
