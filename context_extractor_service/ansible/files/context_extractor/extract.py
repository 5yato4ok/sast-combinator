from __future__ import annotations
from typing import Dict, Any, Optional
from pathlib import Path
from urllib.parse import urlparse
from tree_sitter import Node

from .ts_utils import (
    detect_language, create_parser, line_range,
    find_enclosing_function, find_deepest_node_at_line,
    inject_html_script_source, node_text,
)
from .config import LANG_NODESETS
from .io import load_source_from_url


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

    def promote_single_line_control_body(node: Optional[Node]) -> Optional[Node]:
        if node is None:
            return None
        if lang_key == "python":
            return node
        control_types = {
            "if_statement", "for_statement", "for_in_statement", "for_of_statement",
            "while_statement", "do_statement",
        }
        current_line = line_number - 1
        current = node
        while current is not None:
            if current.type in control_types and current.start_point[0] == current_line:
                header_has_call = False
                stack = [current]
                while stack:
                    child = stack.pop()
                    if child.start_point[0] != current_line:
                        continue
                    if child.type in {"call_expression", "method_invocation", "call"}:
                        header_has_call = True
                        break
                    stack.extend(child.children)
                if header_has_call:
                    return node
                body_children = [
                    child for child in current.children
                    if child.start_point[0] > current.start_point[0]
                    and child.type not in {"comment", "{", "}", ";", "if", "for", "while", "do"}
                ]
                if len(body_children) == 1:
                    return body_children[0]
                return node
            current = current.parent
        return node

    node_at_line = promote_single_line_control_body(node_at_line)

    # Climb up from the smallest node to find a multi-line data literal or
    # expression that is worth returning as "code on line".  For everything
    # else (control flow, statements, blocks) fall back to the source line.
    def climb_to_multiline(node: Optional[Node]) -> Optional[Node]:
        # For SAST triage, showing the exact source line is usually more useful
        # than expanding to a larger AST fragment. Preserve full multiline text
        # only for expression families where the target line would otherwise
        # lose essential context by snapping to a nested subtree or a trailing
        # continuation line.
        expression_chain_types = frozenset({
            "binary_expression", "boolean_operator", "comparison_operator",
            "conditional_expression", "ternary_expression",
        })
        continuation_expression_types = {
            "assignment_expression",
            "augmented_assignment_expression",
            "compound_assignment_expression",
        }
        multiline_candidate: Optional[Node] = None
        target_line_0 = line_number - 1
        current = node
        while current is not None:
            s, e = line_range(current)
            if e > s:
                is_expression_chain = current.type in expression_chain_types
                is_continuation_expression = (
                    lang_key == "cpp"
                    and current.type in continuation_expression_types
                    and target_line_0 > current.start_point[0]
                )
                if is_expression_chain or is_continuation_expression:
                    multiline_candidate = current
            current = current.parent
        return multiline_candidate

    code_on_line: Optional[str] = None
    lines = source_code.splitlines()

    multiline_node = climb_to_multiline(node_at_line)
    if multiline_node:
        # return entire multi-line node text
        code_on_line = source_bytes[multiline_node.start_byte: multiline_node.end_byte].decode(
            "utf-8", errors="replace"
        )
    elif node_at_line:
        # fallback: single-line node → return full source line
        line_index = node_at_line.start_point[0]
        if 0 <= line_index < len(lines):
            code_on_line = lines[line_index]
    else:
        # fallback: no node at all
        if 1 <= line_number <= len(lines):
            code_on_line = lines[line_number - 1]


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
