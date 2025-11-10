from __future__ import annotations
from typing import Iterable, Tuple, Set, List, Optional, Dict, Any
from pathlib import Path
from tree_sitter import Node

from .config import LANG_NODESETS
from .ts_utils import detect_language, create_parser, line_range
from .comments import compute_comment_lines, mask_code_keep_comment
from .header import collect_multiline_header
from .indent import dedent_minimum
from .identifiers import (
    is_function_like, is_block_like, is_key_stmt, is_loop,
    collect_idents_in_node, split_reads_writes
)


def compress_function_from_source(
    source_code: str,
    filename: str,
    line_number: int,
    *,
    max_backward_depth: int = 2,
    markers: Optional[Dict[str, str]] = None,
    preserve_inline_comments: bool = True,
    include_control_headers: bool = True,
) -> Dict[str, Any]:
    """
    Produce a compact snippet of the function containing `line_number`.

    Key properties:
      - Multi-line headers (up to '{' for C-like; 'def ...:' for Python).
      - Backward expansion by identifier reads/writes with member/field awareness.
      - Keeps ALL comment-only lines within the function.
      - Optionally keeps inline comments for omitted lines (code masked to '…').
      - Ensures control headers (for/if/while/…) are present when their bodies are relevant.
    """
    # --- Guards ---
    if line_number <= 0:
        return {"text": "// Invalid line number (must be 1-based and > 0).", "meta": {"target_line": line_number}}
    lines = source_code.splitlines()
    if not lines:
        return {"text": "// Empty source.", "meta": {"target_line": line_number}}
    if line_number > len(lines):
        return {"text": "// Target line beyond end of file.", "meta": {"target_line": line_number}}

    source_bytes = source_code.encode("utf-8", errors="replace")

    # --- Language & parser ---
    try:
        lang, lang_key = detect_language(Path(filename))
    except Exception as e:
        return {"text": f"// {e}", "meta": {"target_line": line_number}}
    parser = create_parser(lang)  # critical: initialize Parser(Language) directly
    tree = parser.parse(source_bytes)
    nodeset = LANG_NODESETS[lang_key]

    # --- Comment prefix ---
    line_comment = nodeset["line_comment_prefix"]
    if markers and markers.get("line_comment"):
        line_comment = markers["line_comment"]

    # --- Find function and target nodes ---
    def find_function_node(n: Node) -> Optional[Node]:
        if is_function_like(n, nodeset):
            s, e = line_range(n)
            if s + 1 <= line_number <= e + 1:
                return n
        for c in n.children:
            fn = find_function_node(c)
            if fn:
                return fn
        return None

    def find_target_node(n: Node) -> Optional[Node]:
        s, e = line_range(n)
        if s <= (line_number - 1) <= e:
            for c in n.children:
                hit = find_target_node(c)
                if hit:
                    return hit
            return n
        return None

    func_node = find_function_node(tree.root_node)
    if not func_node:
        return {"text": f"{line_comment} Function not found.", "meta": {"language": lang_key, "target_line": line_number}}

    target_node = find_target_node(func_node)
    if not target_node:
        f_start, f_end = line_range(func_node)
        return {
            "text": f"{line_comment} Target line not found in function.",
            "meta": {"language": lang_key, "function_lines": (f_start + 1, f_end + 1), "target_line": line_number},
        }

    # --- Seed identifiers & expansion ---
    seed_reads, seed_writes = split_reads_writes(target_node, source_bytes, lang_key, nodeset)
    seed_all_sorted = sorted((seed_reads | seed_writes))

    # Mark target node lines as relevant
    relevant_lines: Set[int] = set(range(target_node.start_point[0], target_node.end_point[0] + 1))

    # Collect ancestor blocks (including the function)
    nodes_to_visit: List[Node] = []
    p: Optional[Node] = target_node
    while p is not None:
        if is_block_like(p, nodeset) or is_function_like(p, nodeset):
            nodes_to_visit.append(p)
        p = p.parent

    frontier_reads: Set[str] = set(seed_reads)
    frontier_writes: Set[str] = set(seed_writes)
    seen_reads: Set[str] = set()
    seen_writes: Set[str] = set()

    control_set = nodeset.get("control", set())

    def promote_control_ancestors(n: Node):
        """
        When a key statement matches, ensure control headers (for/if/while/…) up the parent chain are included.
        Important: don't stop at the first block — for/if bodies are often blocks.
        """
        q = n.parent
        seen_first_block = False
        while q is not None and not is_function_like(q, nodeset):
            if q.type in control_set:
                qs, qe = line_range(q)
                for j in range(qs, qe + 1):
                    relevant_lines.add(j)
            if is_block_like(q, nodeset) and not seen_first_block:
                pc = q.parent
                if pc is not None and pc.type in control_set:
                    ps, pe = line_range(pc)
                    for j in range(ps, pe + 1):
                        relevant_lines.add(j)
                seen_first_block = True
            q = q.parent

    def mark_if_references_ids(root: Node, idset: Set[str]) -> tuple[bool, Set[str], Set[str]]:
        matched_any = False
        discovered_reads: Set[str] = set()
        discovered_writes: Set[str] = set()
        stack: List[Node] = [root]
        while stack:
            n = stack.pop()
            if is_key_stmt(n, nodeset):
                all_ids = collect_idents_in_node(n, source_bytes, nodeset)
                if idset & all_ids:
                    matched_any = True
                    s, e = line_range(n)
                    for i in range(s, e + 1):
                        relevant_lines.add(i)
                    r, w = split_reads_writes(n, source_bytes, lang_key, nodeset)
                    discovered_reads |= r
                    discovered_writes |= w
                    if include_control_headers:
                        promote_control_ancestors(n)
            stack.extend(n.children)
        return matched_any, discovered_reads, discovered_writes

    depth = 0
    while depth < max_backward_depth and (frontier_reads - seen_reads or frontier_writes - seen_writes):
        current_ids = (frontier_reads - seen_reads) | (frontier_writes - seen_writes)
        new_reads: Set[str] = set()
        new_writes: Set[str] = set()
        any_match = False
        for blk in nodes_to_visit:
            matched, r, w = mark_if_references_ids(blk, current_ids)
            if matched:
                any_match = True
                new_reads |= r
                new_writes |= w
        seen_reads |= (frontier_reads - seen_reads)
        seen_writes |= (frontier_writes - seen_writes)
        frontier_reads |= new_reads
        frontier_writes |= new_writes
        depth += 1
        if not any_match:
            break

    # --- Always keep comment-only lines within the function ---
    f_start, f_end = line_range(func_node)
    comment_only_lines = compute_comment_lines(lang_key, lines)
    for i in range(f_start, f_end + 1):
        if i in comment_only_lines:
            relevant_lines.add(i)

    # --- BUGFIX (AST-level post pass): ensure headers of controls are present if their bodies are relevant ---
    if include_control_headers and control_set:
        def ensure_control_headers_for_relevant_bodies(root: Node):
            stack_ctrl: List[Node] = [root]
            while stack_ctrl:
                n = stack_ctrl.pop()
                if n.type in control_set:
                    # Find a body-like child (block or single statement) and check intersection with relevant_lines
                    body: Optional[Node] = None
                    for ch in n.children:
                        # prefer explicit block bodies
                        if is_block_like(ch, nodeset):
                            body = ch
                            break
                    if body is None:
                        # fallback: any child that is not part of the header (heuristic: has its own lines)
                        # and not itself a control keyword token
                        candidates = [ch for ch in n.children if ch.end_point[0] > n.start_point[0]]
                        if candidates:
                            # pick the earliest such candidate
                            body = min(candidates, key=lambda c: c.start_point[0])
                    if body is not None:
                        bs, be = line_range(body)
                        if any((k in relevant_lines) for k in range(bs, be + 1)):
                            hs, _ = line_range(n)  # header line index
                            relevant_lines.add(hs)
                stack_ctrl.extend(n.children)
        ensure_control_headers_for_relevant_bodies(func_node)

    # --- Merge relevant lines into contiguous blocks ---
    blocks: List[Tuple[int, int]] = []
    if relevant_lines:
        sorted_lines = sorted(relevant_lines)
        start = prev = sorted_lines[0]
        for i in sorted_lines[1:]:
            if i == prev + 1:
                prev = i
            else:
                blocks.append((start, prev))
                start = prev = i
        blocks.append((start, prev))

    # --- Build output ---
    header_lines, cursor = collect_multiline_header(lines, lang_key, f_start, f_end)

    out: List[str] = []
    out.extend(header_lines)

    def nonempty_present(slice_lines: Iterable[str]) -> bool:
        return any(l.strip() for l in slice_lines)

    def comment_omitted() -> str:
        return f"{line_comment} ... omitted ..."

    def emit_skipped_region_with_inline_comments(lo: int, hi: int):
        if lo >= hi:
            return
        slice_lines = lines[lo:hi]
        if not nonempty_present(slice_lines):
            return
        out.append(comment_omitted())
        if preserve_inline_comments:
            for j in range(lo, hi):
                masked = mask_code_keep_comment(lines[j], lang_key)
                if masked:
                    out.append(masked)

    for start, end in blocks:
        if start < cursor:
            start = max(start, cursor)
            if start > end:
                continue
        emit_skipped_region_with_inline_comments(cursor, start)
        for i in range(start, end + 1):
            if lines[i].strip() or i in comment_only_lines:
                out.append(lines[i])
        cursor = end + 1

    emit_skipped_region_with_inline_comments(cursor, f_end)

    if LANG_NODESETS[lang_key]["closing_is_brace"]:
        out.append(lines[f_end])

    out = dedent_minimum(out)

    meta = {
        "language": lang_key,
        "function_lines": (f_start + 1, f_end + 1),
        "header_lines": (f_start + 1, f_start + len(header_lines)),
        "target_line": line_number,
        "identifiers": {
            "seed": seed_all_sorted,
            "reads": sorted(frontier_reads),
            "writes": sorted(frontier_writes),
        },
        "blocks": [(a + 1, b + 1) for (a, b) in blocks],
        "preserve_inline_comments": preserve_inline_comments,
    }
    return {"text": "\n".join(out), "meta": meta}
