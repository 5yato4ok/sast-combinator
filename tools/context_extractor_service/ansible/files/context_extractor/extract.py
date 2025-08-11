from __future__ import annotations
from typing import Dict, Any, Optional
from pathlib import Path
from urllib.parse import urlparse
from tree_sitter import Node

from .ts_utils import detect_language, create_parser, line_range
from .config import LANG_NODESETS
from .io import load_source_from_url

def extract_function_from_source(source_code: str, filename: str, line_number: int, max_lines) -> Dict[str, Any]:
    from . import compress_function_from_source
    if line_number <= 0:
        return {"text": "// Invalid line number (must be 1-based and > 0).", "meta": {"target_line": line_number}}
    if not source_code:
        return {"text": "// Empty source.", "meta": {"target_line": line_number}}

    try:
        lang, lang_key = detect_language(Path(filename))
    except Exception as e:
        return {"text": f"// {e}", "meta": {"target_line": line_number}}

    parser = create_parser(lang)
    source_bytes = source_code.encode("utf-8", errors="replace")
    tree = parser.parse(source_bytes)

    nodeset = LANG_NODESETS[lang_key]
    func_types = nodeset["function"]

    def is_function_like(n: Node) -> bool:
        return n.type in func_types

    def find_enclosing_function(n: Node) -> Optional[Node]:
        s, e = line_range(n)
        if not (s + 1 <= line_number <= e + 1):
            return None
        if is_function_like(n):
            return n
        for ch in n.children:
            hit = find_enclosing_function(ch)
            if hit:
                return hit
        return None

    func_node = find_enclosing_function(tree.root_node)
    if not func_node:
        return {"text": "// Function not found.", "meta": {"language": lang_key, "target_line": line_number}}

    f_start, f_end = line_range(func_node)
    text = source_bytes[func_node.start_byte: func_node.end_byte].decode("utf-8", errors="replace")
    relative_line_number = (line_number - (f_start + 1)) + 1

    return {
        "text": text,
        "meta": {
            "language": lang_key,
            "function_lines": (f_start + 1, f_end + 1),
            "target_line": line_number,
            "relative_line_number": relative_line_number,
        },
    }

def extract_function(file_url: str, line_number: int, max_lines: int = 100) -> Dict[str, Any]:
    src = load_source_from_url(file_url)
    filename = Path(urlparse(file_url).path).name
    return extract_function_from_source(src, filename, line_number, max_lines)

def compress_function(file_url: str, line_number: int) -> Dict[str, Any]:
    from .compress import compress_function_from_source
    src = load_source_from_url(file_url)
    filename = Path(urlparse(file_url).path).name
    return compress_function_from_source(src, filename, line_number)
