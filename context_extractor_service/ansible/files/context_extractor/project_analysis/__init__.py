"""Public facade for project-wide context-extractor analysis helpers."""
from __future__ import annotations

from .callers import find_callers
from .classification import classify_file
from .navigation import (
    _imports_from_ast,
    _imports_from_regex,
    find_decorators,
    find_definition,
    find_imports,
    find_route_to_function,
    get_file_structure,
)
from .shared import _iter_source_files, _try_parse
from .trace import trace_identifier_backward
