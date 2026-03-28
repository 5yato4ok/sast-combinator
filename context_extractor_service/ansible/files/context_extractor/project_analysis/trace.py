from __future__ import annotations

import operator
from pathlib import Path
from typing import Any

from ..config import LANG_NODESETS
from ..identifiers import collect_idents_in_node, is_assign, is_key_stmt, split_reads_writes
from .shared import _find_func_node, _parse_required
from ..ts_utils import detect_language, inject_html_script_source

_INLINE_FUNCTION_BINDING_TYPES = frozenset({
    "arrow_function", "lambda_expression", "lambda",
    "anonymous_function_creation_expression",
    "anonymous_method_expression",
})

def trace_identifier_backward(
    source: str,
    filepath: Path,
    line_number: int,
    identifier: str,
    max_depth: int = 3,
) -> list[dict[str, Any]]:
    tree, lang_key, src_bytes = _parse_required(source, filepath)
    if tree and lang_key == "html":
        html_lang, _html_key = detect_language(filepath)
        lang, lang_key, source, line_number = inject_html_script_source(
            source, line_number, html_lang, lang_key,
        )
        tree, lang_key, src_bytes = _parse_required(source, Path("inline-script.js"))
    return _trace_ast(tree.root_node, lang_key, src_bytes, source, line_number, identifier, max_depth)


def _trace_ast(
    root,
    lang_key: str,
    src_bytes: bytes,
    source: str,
    line_number: int,
    identifier: str,
    max_depth: int,
) -> list[dict[str, Any]]:
    nodeset = LANG_NODESETS[lang_key]
    func_types = nodeset.get("function", set())
    func_node = _find_func_node(root, line_number, func_types)
    search_root = func_node or root

    stmts: list[tuple[int, Any]] = []
    _collect_key_stmts(search_root, nodeset, stmts)
    stmts.sort(key=operator.itemgetter(0))

    lines = source.splitlines()
    chain: list[dict[str, Any]] = []
    targets = {identifier}
    initial_target_line = line_number
    target_stmt = next((stmt for stmt_line, stmt in stmts if stmt_line + 1 == line_number), None)
    stop_after_first_hop = bool(
        target_stmt is not None and target_stmt.type in {"if_statement", "while_statement", "do_statement"}
    )

    for _depth in range(max_depth):
        found = False
        for stmt_line, stmt_node in reversed(stmts):
            if stmt_line + 1 > line_number:
                continue
            reads, writes = split_reads_writes(stmt_node, src_bytes, lang_key, nodeset)
            overlap = writes & targets
            if not overlap:
                continue
            if (
                stmt_line + 1 == line_number
                and _is_indirect_pointer_write_site(stmt_node, src_bytes, lang_key, nodeset, overlap)
            ):
                continue
            code = lines[stmt_line] if stmt_line < len(lines) else ""
            chain.append({
                "line": stmt_line + 1,
                "code": code.strip(),
                "writes": sorted(overlap),
                "reads": sorted(reads),
            })
            if stop_after_first_hop:
                return chain
            next_targets = reads - writes
            if stmt_node.type in nodeset.get("loop", set()):
                loop_reads = _collect_loop_source_reads(stmt_node, src_bytes, nodeset)
                if loop_reads:
                    next_targets = loop_reads
            if (
                stmt_node.type in nodeset.get("loop", set())
                and _all_targets_bind_to_constant_locals(
                    stmts,
                    src_bytes,
                    lang_key,
                    nodeset,
                    stmt_line + 1,
                    next_targets,
                )
            ):
                return chain
            targets = next_targets
            line_number = stmt_line
            found = True
            break
        if not found or not targets:
            break

    if chain:
        return chain

    function_binding_chain = _trace_function_binding_at_line(
        func_node,
        lines,
        src_bytes,
        lang_key,
        nodeset,
        line_number,
        identifier,
    )
    if function_binding_chain:
        return function_binding_chain

    nested_function_binding_chain = _trace_nested_function_binding_at_line(
        search_root,
        lines,
        src_bytes,
        lang_key,
        nodeset,
        line_number,
        identifier,
    )
    if nested_function_binding_chain:
        return nested_function_binding_chain

    return _trace_declaration_at_line(stmts, nodeset, lines, src_bytes, lang_key, line_number, identifier)


def _trace_declaration_at_line(
    stmts: list[tuple[int, Any]],
    nodeset: dict[str, Any],
    lines: list[str],
    src_bytes: bytes,
    lang_key: str,
    line_number: int,
    identifier: str,
) -> list[dict[str, Any]]:
    for stmt_line, stmt_node in stmts:
        if stmt_line + 1 != line_number:
            continue
        if stmt_node.type not in nodeset.get("declaration", set()):
            continue
        reads, writes = split_reads_writes(stmt_node, src_bytes, lang_key, nodeset)
        overlap = writes & {identifier}
        if overlap:
            code = lines[stmt_line] if stmt_line < len(lines) else ""
            return [{
                "line": stmt_line + 1,
                "code": code.strip(),
                "writes": sorted(overlap),
                "reads": sorted(reads),
            }]
    return []


def _trace_function_binding_at_line(
    func_node,
    lines: list[str],
    src_bytes: bytes,
    lang_key: str,
    nodeset: dict[str, Any],
    line_number: int,
    identifier: str,
) -> list[dict[str, Any]]:
    if func_node is None:
        return []
    if func_node.type not in _INLINE_FUNCTION_BINDING_TYPES:
        return []
    params = func_node.child_by_field_name("parameters")
    if params is None:
        params = next(
            (child for child in func_node.children if child.type in {"implicit_parameter", "parameter", "parameter_list"}),
            None,
        )
    if params is None:
        return []
    start_line = params.start_point[0] + 1
    end_line = params.end_point[0] + 1
    if not (start_line <= line_number <= end_line):
        return []
    reads, writes = split_reads_writes(func_node, src_bytes, lang_key, nodeset)
    overlap = writes & {identifier}
    if not overlap:
        return []
    code = lines[line_number - 1] if 0 < line_number <= len(lines) else ""
    return [{
        "line": line_number,
        "code": code.strip(),
        "writes": sorted(overlap),
        "reads": sorted(reads - overlap),
    }]


def _trace_nested_function_binding_at_line(
    root,
    lines: list[str],
    src_bytes: bytes,
    lang_key: str,
    nodeset: dict[str, Any],
    line_number: int,
    identifier: str,
) -> list[dict[str, Any]]:
    candidate = _find_deepest_inline_function_covering_line(root, line_number)
    if candidate is None:
        return []
    reads, writes = split_reads_writes(candidate, src_bytes, lang_key, nodeset)
    overlap = writes & {identifier}
    if not overlap:
        return []
    binding_node = _inline_function_binding_node(candidate)
    binding_line = binding_node.start_point[0] + 1
    if line_number <= binding_line:
        return []
    code = lines[binding_line - 1] if 0 < binding_line <= len(lines) else ""
    return [{
        "line": binding_line,
        "code": code.strip(),
        "writes": sorted(overlap),
        "reads": sorted(reads - overlap),
    }]


def _find_deepest_inline_function_covering_line(root, line_number: int):
    best = None
    stack = [root]
    while stack:
        current = stack.pop()
        start_line = current.start_point[0] + 1
        end_line = current.end_point[0] + 1
        if not (start_line <= line_number <= end_line):
            continue
        if current.type in _INLINE_FUNCTION_BINDING_TYPES:
            best = current
        stack.extend(current.children)
    return best


def _inline_function_binding_node(func_node):
    params = func_node.child_by_field_name("parameters")
    if params is not None:
        return params
    for child in func_node.children:
        if child.type in {"implicit_parameter", "parameter", "parameter_list", "formal_parameters"}:
            return child
    return func_node


def _all_targets_bind_to_constant_locals(
    stmts: list[tuple[int, Any]],
    src_bytes: bytes,
    lang_key: str,
    nodeset: dict[str, Any],
    line_number: int,
    targets: set[str],
) -> bool:
    if not targets:
        return False
    for target in targets:
        binding_found = False
        for stmt_line, stmt_node in reversed(stmts):
            if stmt_line + 1 >= line_number:
                continue
            reads, writes = split_reads_writes(stmt_node, src_bytes, lang_key, nodeset)
            if target not in writes:
                continue
            binding_found = True
            if reads:
                return False
            break
        if not binding_found:
            return False
    return True


def _collect_loop_source_reads(stmt_node, src_bytes: bytes, nodeset: dict[str, Any]) -> set[str]:
    right = stmt_node.child_by_field_name("right")
    if right is not None:
        return collect_idents_in_node(right, src_bytes, nodeset)
    left = stmt_node.child_by_field_name("left")
    body = stmt_node.child_by_field_name("body")
    reads: set[str] = set()
    for child in stmt_node.children:
        if child == left or child == body:
            continue
        reads |= collect_idents_in_node(child, src_bytes, nodeset)
    return reads


def _is_indirect_pointer_write_site(
    stmt_node,
    src_bytes: bytes,
    lang_key: str,
    nodeset: dict[str, Any],
    overlap: set[str],
) -> bool:
    stack = [stmt_node]
    while stack:
        current = stack.pop()
        if is_assign(current, nodeset) and current.child_count >= 3:
            lhs = current.children[0]
            if lhs.type == "pointer_expression":
                lhs_ids = collect_idents_in_node(lhs, src_bytes, nodeset)
                if lhs_ids & overlap:
                    return True
        stack.extend(current.children)
    return False


def _collect_key_stmts(node, nodeset: dict, out: list):
    stack = [node]
    stmt_types = nodeset.get("key", set()) | nodeset.get("declaration", set())
    while stack:
        current = stack.pop()
        if current.type in stmt_types:
            out.append((current.start_point[0], current))
        stack.extend(current.children)
