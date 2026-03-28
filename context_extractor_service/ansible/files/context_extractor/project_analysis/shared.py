from __future__ import annotations

import os
from pathlib import Path

from ..config import LANG_NODESETS, SKIP_DIRS
from .symbols import _find_deepest_node_covering_line, _get_node_name, _is_callable_binding_node
from ..ts_utils import create_parser, detect_language, find_enclosing_function


_SKIP_DIRS = SKIP_DIRS
_SOURCE_EXTS = frozenset({
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".java", ".kt", ".scala",
    ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp",
    ".cs", ".go", ".rs", ".rb",
    ".php", ".swift", ".m", ".mm",
    ".lua", ".pl", ".pm", ".r", ".R",
    ".dart", ".ex", ".exs", ".erl", ".hrl",
    ".zig", ".nim", ".v", ".vala",
    ".qml",
})
_MAX_RESULTS = 50
_SNIPPET_CONTEXT = 2


def _iter_source_files(source_dir: Path):
    for dirpath, dirnames, filenames in os.walk(source_dir):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() in _SOURCE_EXTS:
                yield fpath.relative_to(source_dir)


def _snippet(lines: list[str], line_0: int, ctx: int = _SNIPPET_CONTEXT) -> str:
    start = max(0, line_0 - ctx)
    end = min(len(lines), line_0 + ctx + 1)
    parts: list[str] = []
    for i in range(start, end):
        marker = ">>>" if i == line_0 else "   "
        parts.append(f"{marker} {i + 1:>5}| {lines[i]}")
    return "\n".join(parts)


def _try_parse(source: str, filepath: Path):
    try:
        lang, lang_key = detect_language(filepath)
    except ValueError:
        return None, None, None
    parser = create_parser(lang)
    source_bytes = source.encode("utf-8", errors="replace")
    tree = parser.parse(source_bytes)
    return tree, lang_key, source_bytes


def _parse_required(source: str, filepath: Path):
    lang, lang_key = detect_language(filepath)
    parser = create_parser(lang)
    source_bytes = source.encode("utf-8", errors="replace")
    tree = parser.parse(source_bytes)
    if tree.root_node.has_error:
        msg = f"Failed to parse file: {filepath}"
        raise ValueError(msg)
    return tree, lang_key, source_bytes


def _find_enclosing_function_name(root, line_number: int, lang_key: str) -> str | None:
    nodeset = LANG_NODESETS.get(lang_key, {})
    func_types = nodeset.get("function", set())

    func_node = find_enclosing_function(root, line_number, func_types)
    if func_node is not None:
        if func_node.type == "arrow_function":
            return None
        name = _get_node_name(func_node, root.text)
        return name if name != "<anonymous>" else None

    current = _find_deepest_node_covering_line(root, line_number)
    while current is not None:
        if _is_callable_binding_node(current, lang_key, root.text):
            name = _get_node_name(current, root.text)
            return name if name != "<anonymous>" else None
        current = current.parent
    return None


def _find_func_node(root, line_number: int, func_types: set):
    return find_enclosing_function(root, line_number, func_types)
