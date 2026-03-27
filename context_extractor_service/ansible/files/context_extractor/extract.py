from __future__ import annotations
from typing import Dict, Any, Optional
from pathlib import Path
from urllib.parse import urlparse
from tree_sitter import Node

from .ts_utils import (
    detect_language, create_parser, line_range,
    find_enclosing_function, find_deepest_node_at_line,
    inject_html_script_source, promote_single_statement_control_body,
)
from .config import LANG_NODESETS
from .io import load_source_from_url


_CONTROL_TYPES = frozenset({
    "if_statement",
    "for_statement",
    "for_in_statement",
    "for_of_statement",
    "while_statement",
    "do_statement",
})

_CONTROL_PROMOTION_CALL_TYPES = frozenset({
    "call_expression",
    "method_invocation",
    "call",
})

_CONTROL_PROMOTION_EXCLUDED_BODY_TYPES = frozenset({
    "comment",
    "{",
    "}",
    ";",
    "if",
    "for",
    "while",
    "do",
})

_MULTILINE_EXPRESSION_CHAIN_TYPES = frozenset({
    "binary_expression",
    "boolean_operator",
    "comparison_operator",
    "conditional_expression",
    "ternary_expression",
})

_MULTILINE_CONTINUATION_EXPRESSION_TYPES = frozenset({
    "assignment_expression",
    "augmented_assignment_expression",
    "compound_assignment_expression",
})


def _promote_single_line_control_body(node: Node | None, line_number: int, nodeset) -> Node | None:
    if node is None or not nodeset["closing_is_brace"]:
        return node
    current_line = line_number - 1
    current = node
    while current is not None:
        if current.type in _CONTROL_TYPES and current.start_point[0] == current_line:
            return promote_single_statement_control_body(
                current,
                _CONTROL_PROMOTION_CALL_TYPES,
                _CONTROL_PROMOTION_EXCLUDED_BODY_TYPES,
            )
        current = current.parent
    return node


def _find_multiline_candidate(node: Node | None, line_number: int) -> Node | None:
    multiline_candidate: Node | None = None
    target_line_0 = line_number - 1
    current = node
    while current is not None:
        start_line, end_line = line_range(current)
        if end_line > start_line:
            is_expression_chain = current.type in _MULTILINE_EXPRESSION_CHAIN_TYPES
            is_continuation_expression = (
                current.type in _MULTILINE_CONTINUATION_EXPRESSION_TYPES
                and target_line_0 > current.start_point[0]
            )
            if is_expression_chain or is_continuation_expression:
                multiline_candidate = current
        current = current.parent
    return multiline_candidate


def _resolve_code_on_line(
    source_code: str,
    source_bytes: bytes,
    node_at_line: Node | None,
    line_number: int,
) -> str | None:
    lines = source_code.splitlines()
    multiline_node = _find_multiline_candidate(node_at_line, line_number)
    if multiline_node is not None:
        return source_bytes[multiline_node.start_byte: multiline_node.end_byte].decode(
            "utf-8",
            errors="replace",
        )
    if node_at_line is not None:
        line_index = node_at_line.start_point[0]
        if 0 <= line_index < len(lines):
            return lines[line_index]
        return None
    if 1 <= line_number <= len(lines):
        return lines[line_number - 1]
    return None


def extract_function_from_source(source_code: str, filename: str, line_number: int, max_lines) -> Dict[str, Any]:
    if line_number <= 0:
        return {"text": "// Invalid line number (must be 1-based and > 0).", "meta": {"target_line": line_number}}
    if not source_code:
        return {"text": "// Empty source.", "meta": {"target_line": line_number}}

    try:
        lang, lang_key = detect_language(Path(filename))
    except Exception as e:
        return {"text": f"// {e}", "meta": {"target_line": line_number}}

    lang, lang_key, source_code, line_number = inject_html_script_source(
        source_code, line_number, lang, lang_key,
    )

    parser = create_parser(lang)
    source_bytes = source_code.encode("utf-8", errors="replace")
    tree = parser.parse(source_bytes)

    nodeset = LANG_NODESETS[lang_key]
    func_types = nodeset["function"]

    func_node = find_enclosing_function(tree.root_node, line_number, func_types)

    search_root = func_node if func_node is not None else tree.root_node
    node_at_line = find_deepest_node_at_line(search_root, line_number)
    node_at_line = _promote_single_line_control_body(node_at_line, line_number, nodeset)
    code_on_line = _resolve_code_on_line(source_code, source_bytes, node_at_line, line_number)

    if not func_node:
        return {
            "text": "// Function not found.",
            "meta": {"language": lang_key, "target_line": line_number, "code_on_line": code_on_line},
        }

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
            "code_on_line": code_on_line,
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
