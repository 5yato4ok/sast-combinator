"""Context extractor package.

Make the package init lightweight to avoid circular imports during test collection.
We don't import submodules at import time. If someone needs symbols at the package
root (back-compat), we expose them lazily via __getattr__.
"""

# Keep the namespace minimal at import time.
__all__ = []

# Optional: lazy re-exports for backward compatibility (PEP 562, Python 3.7+).
def __getattr__(name: str):
    if name in {
        "extract_function_from_source",
        "extract_function",
        "compress_function",
    }:
        from .extract import (
            extract_function_from_source,
            extract_function,
            compress_function,
        )
        return {
            "extract_function_from_source": extract_function_from_source,
            "extract_function": extract_function,
            "compress_function": compress_function,
        }[name]
    raise AttributeError(name)
from .compress import compress_function_from_source
from .io import load_source_from_url

__all__ = [
]
