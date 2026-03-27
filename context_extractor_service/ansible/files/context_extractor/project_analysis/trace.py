from __future__ import annotations

import operator
import re
from pathlib import Path
from typing import Any

from ..config import LANG_NODESETS
from ..identifiers import is_key_stmt, split_reads_writes
from .shared import _find_func_node, _try_parse
from ..ts_utils import detect_language, inject_html_script_source


def trace_identifier_backward(
    source: str,
    filepath: Path,
    line_number: int,
    identifier: str,
    max_depth: int = 3,
) -> list[dict[str, Any]]:
    tree, lang_key, src_bytes = _try_parse(source, filepath)
    if tree and lang_key == "html":
        html_lang, _html_key = detect_language(filepath)
        lang, lang_key, source, line_number = inject_html_script_source(
            source, line_number, html_lang, lang_key,
        )
        tree, lang_key, src_bytes = _try_parse(source, Path("inline-script.js"))
    if tree and lang_key and src_bytes:
        return _trace_ast(tree.root_node, lang_key, src_bytes, source, line_number, identifier, max_depth)
    return _trace_regex(source, line_number, identifier, max_depth)


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
            if stmt_line + 1 == initial_target_line:
                code = lines[stmt_line].strip() if stmt_line < len(lines) else ""
                if re.match(r"^\*+\s*" + re.escape(identifier) + r"\b", code):
                    continue
            reads, writes = split_reads_writes(stmt_node, src_bytes, lang_key, nodeset)
            overlap = writes & targets
            if not overlap:
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
            targets = reads - writes
            line_number = stmt_line
            found = True
            break
        if not found or not targets:
            break

    if chain:
        return chain

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


def _trace_regex(source: str, line_number: int, identifier: str, max_depth: int) -> list[dict[str, Any]]:
    lines = source.splitlines()
    assign_re = re.compile(r"\b" + re.escape(identifier) + r"\s*[=:]")
    chain: list[dict[str, Any]] = []
    idx = line_number - 2

    for _depth in range(max_depth):
        while idx >= 0:
            if assign_re.search(lines[idx]):
                chain.append({
                    "line": idx + 1,
                    "code": lines[idx].strip(),
                    "writes": [identifier],
                    "reads": [],
                })
                idx -= 1
                break
            idx -= 1
        else:
            break
    return chain


def _collect_key_stmts(node, nodeset: dict, out: list):
    stack = [node]
    while stack:
        current = stack.pop()
        if is_key_stmt(current, nodeset):
            out.append((current.start_point[0], current))
        stack.extend(current.children)
