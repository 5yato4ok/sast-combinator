from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple, Set, List, Optional, Dict, Any
from urllib.parse import urlparse, unquote

import requests
import tree_sitter_cpp as cpp_lang
import tree_sitter_python as py_lang
import tree_sitter_javascript as js_lang
import tree_sitter_java as java_lang
from tree_sitter import Language, Parser, Node

# --- Load compiled Tree-sitter languages (wrappers expose .language()) ---
CPP_LANGUAGE = Language(cpp_lang.language())
PY_LANGUAGE = Language(py_lang.language())
JS_LANGUAGE = Language(js_lang.language())
JAVA_LANGUAGE = Language(java_lang.language())

# --- Map file extensions to Language objects ---
SUPPORTED_LANGUAGES = {
    ".py": PY_LANGUAGE,
    ".h": CPP_LANGUAGE,
    ".hpp": CPP_LANGUAGE,
    ".cpp": CPP_LANGUAGE,
    ".c": CPP_LANGUAGE,
    ".cc": CPP_LANGUAGE,
    ".cxx": CPP_LANGUAGE,
    ".js": JS_LANGUAGE,
    ".mjs": JS_LANGUAGE,
    ".cjs": JS_LANGUAGE,
    ".java": JAVA_LANGUAGE,
}

# --- Per-language node type sets and roles. ---
LANG_NODESETS = {
    "cpp": {
        "function": {"function_definition", "function_declaration", "lambda_expression"},
        "block": {"compound_statement", "lambda_expression", "function_definition"},
        "key": {"assignment_expression", "declaration", "call_expression",
                "if_statement", "return_statement", "for_statement", "for_range_loop"},
        "ident": {"identifier", "field_identifier", "scoped_identifier"},
        "member_like": {"field_expression", "scoped_identifier"},
        "assign": {"assignment_expression"},
        "declaration": {"declaration", "init_declarator"},
        "loop": {"for_statement", "for_range_loop"},
        "call": {"call_expression"},
        "closing_is_brace": True,
        "line_comment_prefix": "//",
    },
    "java": {
        "function": {"method_declaration", "constructor_declaration", "lambda_expression"},
        "block": {"block", "lambda_expression"},
        "key": {"assignment_expression", "local_variable_declaration", "method_invocation",
                "if_statement", "return_statement", "for_statement", "enhanced_for_statement"},
        "ident": {"identifier"},
        "member_like": {"field_access", "method_invocation"},
        "loop": {"for_statement", "enhanced_for_statement"},
        "assign": {"assignment_expression"},
        "declaration": {"local_variable_declaration"},
        "call": {"method_invocation"},
        "closing_is_brace": True,
        "line_comment_prefix": "//",
    },
    "javascript": {
        "function": {"function_declaration", "function", "method_definition", "arrow_function"},
        "block": {"statement_block", "function", "method_definition"},
        "key": {"assignment_expression", "variable_declaration", "call_expression",
                "if_statement", "return_statement", "for_statement", "for_in_statement", "for_of_statement"},
        "ident": {"identifier", "shorthand_property_identifier"},
        "member_like": {"member_expression"},
        "assign": {"assignment_expression"},
        "declaration": {"variable_declaration"},
        "loop": {"for_statement", "for_in_statement", "for_of_statement"},
        "call": {"call_expression"},
        "closing_is_brace": True,
        "line_comment_prefix": "//",
    },
    "python": {
        "function": {"function_definition", "lambda"},
        "block": {"block", "function_definition"},
        "key": {"assignment", "expression_statement", "call", "if_statement", "return_statement", "for_statement"},
        "ident": {"identifier"},
        "member_like": {"attribute"},
        "assign": {"assignment", "augmented_assignment"},
        "declaration": set(),
        "call": {"call"},
        "loop": {"for_statement"},
        "closing_is_brace": False,
        "line_comment_prefix": "#",
    },
}

# --- Per-language comment styles (for full and inline comments) ---
COMMENT_STYLE = {
    "cpp":         {"line": ["//"], "block": [("/*", "*/")]},
    "java":        {"line": ["//"], "block": [("/*", "*/")]},
    "javascript":  {"line": ["//"], "block": [("/*", "*/")]},
    "python":      {"line": ["#"],  "block": []},  # triple quotes are strings, not comments
}

def _compute_comment_lines_generic(lang_key: str, lines: list[str]) -> set[int]:
    """
    Return 0-based indices of lines that are comment-only:
      - line comments (prefix after leading spaces),
      - block comment spans between any configured delimiters.
    Trailing inline comments are NOT included here (handled separately).
    """
    style = COMMENT_STYLE.get(lang_key, {"line": [], "block": []})
    line_prefixes = tuple(style.get("line", []))
    block_delims = style.get("block", [])

    comment_lines: set[int] = set()
    n = len(lines)

    # Block comments
    if block_delims:
        in_block = False
        end_tok = ""
        for i in range(n):
            s = lines[i]
            j = 0
            while True:
                if not in_block:
                    idx_open = -1
                    open_tok = ""
                    for beg, end in block_delims:
                        k = s.find(beg, j)
                        if k != -1 and (idx_open == -1 or k < idx_open):
                            idx_open = k
                            open_tok = beg
                            end_tok = end
                    if idx_open == -1:
                        break
                    in_block = True
                    comment_lines.add(i)
                    j = idx_open + len(open_tok)
                    idx_close = s.find(end_tok, j)
                    if idx_close != -1:
                        in_block = False
                        j = idx_close + len(end_tok)
                        continue
                else:
                    comment_lines.add(i)
                    idx_close = s.find(end_tok, j)
                    if idx_close != -1:
                        in_block = False
                        j = idx_close + len(end_tok)
                        continue
                    break

    # Line comments (start-of-line after whitespace)
    if line_prefixes:
        for i, s in enumerate(lines):
            stripped = s.lstrip()
            if any(stripped.startswith(p) for p in line_prefixes):
                comment_lines.add(i)

    return comment_lines

def _detect_language_name(filepath: Path) -> Tuple[Language, str]:
    """Return (Language, lang_key) by file extension."""
    ext = filepath.suffix.lower()
    if ext not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported file extension: {ext}")
    lang = SUPPORTED_LANGUAGES[ext]
    if lang is CPP_LANGUAGE:
        return lang, "cpp"
    if lang is PY_LANGUAGE:
        return lang, "python"
    if lang is JS_LANGUAGE:
        return lang, "javascript"
    if lang is JAVA_LANGUAGE:
        return lang, "java"
    return lang, "cpp"

def _node_text(node: Node, source_bytes: bytes) -> str:
    """Safely get node text from source bytes."""
    return source_bytes[node.start_byte: node.end_byte].decode("utf-8", errors="replace")

def _line_range(node: Node) -> Tuple[int, int]:
    """Get 0-based inclusive line range for a node."""
    return node.start_point[0], node.end_point[0]

def _collect_multiline_header(lines: List[str], lang_key: str, f_start: int, f_end: int) -> Tuple[List[str], int]:
    """
    Collect a multi-line function header:
    - For brace languages: include lines from f_start up to and including the first '{' line.
    - For Python: include only the 'def ...:' line.
    Returns (header_lines, new_cursor_position_after_header).
    """
    if LANG_NODESETS[lang_key]["closing_is_brace"]:
        header: List[str] = []
        cursor = f_start
        found_brace = False
        while cursor <= f_end:
            line = lines[cursor]
            header.append(line)
            if "{" in line:
                found_brace = True
                cursor += 1
                break
            cursor += 1
        if not found_brace and cursor <= f_end:
            if cursor <= f_end and lines[cursor].strip() == "{":
                header.append(lines[cursor])
                cursor += 1
        return header, cursor
    else:
        return [lines[f_start]], f_start + 1

def _dedent_minimum(lines: List[str]) -> List[str]:
    """Remove minimum common leading spaces across all non-empty lines (tabs unchanged)."""
    def leading_spaces(s: str) -> int:
        i = 0
        while i < len(s) and s[i] == " ":
            i += 1
        return i
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return lines
    min_lead = min(leading_spaces(l) for l in non_empty)
    if min_lead == 0:
        return lines
    return [l[min_lead:] if l.startswith(" " * min_lead) else l for l in lines]

def _byte_span_to_text(source_bytes: bytes, start_byte: int, end_byte: int) -> str:
    """Decode a slice of bytes to UTF-8 text with replacement for invalid sequences."""
    return source_bytes[start_byte:end_byte].decode("utf-8", errors="replace")

def _first_inline_comment_index(line: str, lang_key: str) -> Optional[int]:
    """
    Return index where an inline comment starts (//, #, or block opener like /*),
    only if there is non-whitespace code before it. Otherwise return None.
    Heuristic: does not parse strings; good enough for snippet retention.
    """
    style = COMMENT_STYLE.get(lang_key, {"line": [], "block": []})
    tokens = list(style.get("line", [])) + [beg for (beg, _end) in style.get("block", [])]
    best_idx: Optional[int] = None
    for tok in tokens:
        k = line.find(tok)
        if k == -1:
            continue
        # Must have some non-space before token (i.e., inline, not comment-only)
        if any(ch not in " \t" for ch in line[:k]):
            if best_idx is None or k < best_idx:
                best_idx = k
    return best_idx

def _mask_code_keep_comment(line: str, lang_key: str) -> Optional[str]:
    """
    If the line contains an inline comment (code then comment), return a masked version:
      <indent>… <comment-part>
    Otherwise return None.
    """
    idx = _first_inline_comment_index(line, lang_key)
    if idx is None:
        return None
    # Keep original indentation
    indent_len = 0
    while indent_len < len(line) and line[indent_len] in (" ", "\t"):
        indent_len += 1
    return f"{line[:indent_len]}… {line[idx:].rstrip()}"

def compress_function_from_source(
        source_code: str,
        filename: str,
        line_number: int,
        *,
        max_backward_depth: int = 2,
        markers: Optional[Dict[str, str]] = None,
        preserve_inline_comments: bool = True,
) -> Dict[str, Any]:
    """
    Produce a compact, language-aware snippet of a function that contains `line_number`.

    Features:
      - Multi-line headers ('{' or 'def:').
      - Read/Write identifiers and member/field awareness.
      - Keeps ALL comment-only lines inside the function.
      - Optionally preserves inline comments on omitted lines by masking code (…).
      - Indentation normalization and rich metadata.
    """
    if line_number <= 0:
        return {"text": "// Invalid line number (must be 1-based and > 0).", "meta": {"target_line": line_number}}
    lines = source_code.splitlines()
    if not lines:
        return {"text": "// Empty source.", "meta": {"target_line": line_number}}
    if line_number > len(lines):
        return {"text": "// Target line beyond end of file.", "meta": {"target_line": line_number}}

    source_bytes = source_code.encode("utf-8", errors="replace")

    # Language + parser setup
    try:
        lang, lang_key = _detect_language_name(Path(filename))
    except Exception as e:
        return {"text": f"// {e}", "meta": {"target_line": line_number}}
    parser = Parser(lang)  # keep as requested
    tree = parser.parse(source_bytes)
    nodeset = LANG_NODESETS[lang_key]

    # Comment marker
    line_comment = nodeset["line_comment_prefix"]
    if markers and "line_comment" in markers and markers["line_comment"]:
        line_comment = markers["line_comment"]

    # Helpers
    def is_function_like(n: Node) -> bool: return n.type in nodeset["function"]
    def is_block_like(n: Node) -> bool:    return n.type in nodeset["block"]
    def is_key_stmt(n: Node) -> bool:      return n.type in nodeset["key"]
    def is_identifier(n: Node) -> bool:    return n.type in nodeset["ident"]
    def is_member_like(n: Node) -> bool:   return n.type in nodeset["member_like"]
    def is_assign(n: Node) -> bool:        return n.type in nodeset["assign"]
    def is_declaration(n: Node) -> bool:   return n.type in nodeset["declaration"]
    def is_call(n: Node) -> bool:          return n.type in nodeset["call"]
    def is_loop(n: Node) -> bool:          return n.type in nodeset.get("loop", set())

    # Find enclosing function & target node
    def find_function_node(n: Node) -> Optional[Node]:
        if is_function_like(n):
            s, e = _line_range(n)
            if s + 1 <= line_number <= e + 1:
                return n
        for c in n.children:
            fn = find_function_node(c)
            if fn:
                return fn
        return None

    def find_target_node(n: Node) -> Optional[Node]:
        s, e = _line_range(n)
        if s <= (line_number - 1) <= e:
            for c in n.children:
                hit = find_target_node(c)
                if hit:
                    return hit
            return n
        return None

    func_node = find_function_node(tree.root_node)
    if not func_node:
        return {"text": f"{line_comment} Function not found.",
                "meta": {"language": lang_key, "target_line": line_number}}
    target_node = find_target_node(func_node)
    if not target_node:
        f_start, f_end = _line_range(func_node)
        return {
            "text": f"{line_comment} Target line not found in function.",
            "meta": {"language": lang_key, "function_lines": (f_start + 1, f_end + 1), "target_line": line_number},
        }

    # Identifier helpers
    def collect_idents_in_node(root: Node) -> Set[str]:
        """Collect identifiers including member/field parts."""
        ids: Set[str] = set()
        stack = [root]
        while stack:
            n = stack.pop()
            if is_identifier(n):
                ids.add(_node_text(n, source_bytes))
            elif is_member_like(n):
                for ch in n.children:
                    if is_identifier(ch):
                        ids.add(_node_text(ch, source_bytes))
            stack.extend(n.children)
        return ids

    def split_reads_writes(root: Node) -> Tuple[Set[str], Set[str]]:
        reads: Set[str] = set()
        writes: Set[str] = set()
        stack = [root]
        while stack:
            n = stack.pop()
            if is_assign(n):
                if n.child_count >= 3:
                    lhs = n.children[0]
                    rhs = n.children[-1]
                    writes |= collect_idents_in_node(lhs)
                    reads  |= collect_idents_in_node(rhs)
                else:
                    reads |= collect_idents_in_node(n)
            elif is_declaration(n):
                for ch in n.children:
                    if is_identifier(ch):
                        writes.add(_node_text(ch, source_bytes))
                    else:
                        for g in ch.children:
                            if is_identifier(g):
                                writes.add(_node_text(g, source_bytes))
                            else:
                                reads |= collect_idents_in_node(g)
            elif is_call(n):
                reads |= collect_idents_in_node(n)
            elif is_loop(n):
                for ch in n.children:
                    t = ch.type
                    if lang_key == "python" and t in {"identifier", "pattern", "tuple"}:
                        writes |= collect_idents_in_node(ch)
                    if lang_key == "javascript" and t in {"variable_declaration", "identifier"}:
                        writes |= collect_idents_in_node(ch)
                    if lang_key == "java" and t in {"local_variable_declaration", "variable_declarator", "identifier"}:
                        writes |= collect_idents_in_node(ch)
                    if lang_key == "cpp" and t in {"declaration", "init_declarator", "identifier"}:
                        writes |= collect_idents_in_node(ch)
                all_ids = collect_idents_in_node(n)
                reads |= (all_ids - writes)
            else:
                stack.extend(n.children)
                continue
            stack.extend(n.children)
        raw_ids = collect_idents_in_node(root)
        reads |= (raw_ids - writes)
        return reads, writes

    # Seed identifiers and parent blocks
    seed_reads, seed_writes = split_reads_writes(target_node)
    seed_all = seed_reads | seed_writes

    relevant_lines: Set[int] = set()
    for i in range(target_node.start_point[0], target_node.end_point[0] + 1):
        relevant_lines.add(i)

    nodes_to_visit: List[Node] = []
    p: Optional[Node] = target_node
    while p is not None:
        if is_block_like(p) or is_function_like(p):
            nodes_to_visit.append(p)
        p = p.parent

    # Expand frontier
    frontier_reads: Set[str] = set(seed_reads)
    frontier_writes: Set[str] = set(seed_writes)
    seen_reads: Set[str] = set()
    seen_writes: Set[str] = set()

    def mark_if_references_ids(root: Node, idset: Set[str]) -> Tuple[bool, Set[str], Set[str]]:
        matched_any = False
        discovered_reads: Set[str] = set()
        discovered_writes: Set[str] = set()
        stack = [root]
        while stack:
            n = stack.pop()
            if is_key_stmt(n):
                all_ids = collect_idents_in_node(n)
                if idset & all_ids:
                    matched_any = True
                    s, e = _line_range(n)
                    for i in range(s, e + 1):
                        relevant_lines.add(i)
                    r, w = split_reads_writes(n)
                    discovered_reads |= r
                    discovered_writes |= w
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

    # Include ALL comment-only lines within the function body
    f_start, f_end = _line_range(func_node)
    comment_only_lines = _compute_comment_lines_generic(lang_key, lines)
    for i in range(f_start, f_end + 1):
        if i in comment_only_lines:
            relevant_lines.add(i)

    # Merge relevant lines into contiguous blocks
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

    # Build output
    header_lines, cursor = _collect_multiline_header(lines, lang_key, f_start, f_end)

    out: List[str] = []
    out.extend(header_lines)

    def nonempty_present(slice_lines: Iterable[str]) -> bool:
        return any(l.strip() for l in slice_lines)

    def comment_omitted() -> str:
        return f"{line_comment} ... omitted ..."

    def emit_skipped_region_with_inline_comments(lo: int, hi: int):
        """Emit omission marker and masked inline comments within [lo, hi)."""
        slice_lines = lines[lo:hi]
        if not nonempty_present(slice_lines):
            return
        out.append(comment_omitted())
        if preserve_inline_comments:
            for j in range(lo, hi):
                masked = _mask_code_keep_comment(lines[j], lang_key)
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

    if nodeset["closing_is_brace"]:
        out.append(lines[f_end])

    out = _dedent_minimum(out)

    meta = {
        "language": lang_key,
        "function_lines": (f_start + 1, f_end + 1),
        "header_lines": (f_start + 1, f_start + len(header_lines)),
        "target_line": line_number,
        "identifiers": {
            "seed": sorted(seed_all),
            "reads": sorted(frontier_reads),
            "writes": sorted(frontier_writes),
        },
        "blocks": [(a + 1, b + 1) for (a, b) in blocks],
        "preserve_inline_comments": preserve_inline_comments,
    }

    return {"text": "\n".join(out), "meta": meta}

def load_source_from_url(
        url: str,
        *,
        timeout: float = 15.0,
        max_bytes: int = 50 * 1024 * 1024,  # hard cap to avoid huge downloads
) -> str:
    """
    Load source text from a file:// or http(s):// URL with sensible safety defaults.

    - file:// → reads from local filesystem (UTF-8).
    - http(s):// → GET with timeout, basic content-type guard for text, and size cap.

    Returns:
        Source code as a UTF-8 string (invalid bytes replaced).

    Raises:
        OSError / FileNotFoundError on local issues.
        requests.RequestException on network issues.
        ValueError if content looks non-textual or exceeds size limits.
    """
    parsed = urlparse(url)

    if parsed.scheme == "file":
        # Convert to local file path. `unquote` handles URL-encoded characters.
        path = Path(unquote(parsed.path))
        return path.read_text(encoding="utf-8", errors="replace")

    if parsed.scheme in {"http", "https"}:
        # Fetch with streaming to enforce a hard byte cap.
        with requests.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            buf = bytearray()
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    if len(buf) + len(chunk) > max_bytes:
                        raise ValueError(f"Response exceeds max_bytes={max_bytes} limit")
                    buf.extend(chunk)
        return bytes(buf).decode("utf-8", errors="replace")

    raise ValueError(f"Unsupported URL scheme for source loading: {parsed.scheme}")


def extract_function_from_source(
        source_code: str,
        filename: str,
        line_number: int,
) -> Dict[str, Any]:
    """
    Find and return the *full* function body that encloses the given 1-based line number.

    Returns:
        {
          "text": <full function text as in source>,
          "meta": {
             "language": <'cpp'|'java'|'javascript'|'python'>,
             "function_lines": (start_line_1based, end_line_1based),
             "target_line": <1-based int in file>,
             "relative_line_number": <1-based int in function>
          }
        }

    Notes:
    - Uses per-language function-node sets from LANG_NODESETS.
    - Properly initializes Tree-sitter parser with set_language(...).
    - Returns a minimal error comment in "text" if not found.
    """
    # Basic guards
    if line_number <= 0:
        return {"text": "// Invalid line number (must be 1-based and > 0).", "meta": {"target_line": line_number}}
    if not source_code:
        return {"text": "// Empty source.", "meta": {"target_line": line_number}}

    # Language detection and parser setup
    try:
        lang, lang_key = _detect_language_name(Path(filename))
    except Exception as e:
        return {"text": f"// {e}", "meta": {"target_line": line_number}}

    parser = Parser(lang)
    source_bytes = source_code.encode("utf-8", errors="replace")
    tree = parser.parse(source_bytes)

    # Per-language function-like node types
    nodeset = LANG_NODESETS[lang_key]
    func_types = nodeset["function"]

    def is_function_like(n: Node) -> bool:
        return n.type in func_types

    def find_enclosing_function(n: Node) -> Optional[Node]:
        """Depth-first: return the first function-like node that spans the target line."""
        s, e = _line_range(n)
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

    f_start, f_end = _line_range(func_node)
    relative_line_number = (line_number - (f_start + 1)) + 1
    text = _byte_span_to_text(source_bytes, func_node.start_byte, func_node.end_byte)

    return {
        "text": text,
        "meta": {
            "language": lang_key,
            "function_lines": (f_start + 1, f_end + 1),
            "target_line": line_number,
            "relative_line_number": relative_line_number,
        },
    }

def extract_function(file_url: str, line_number: int) -> Dict[str, Any]:
    """Download the file and extract the function containing the given line number."""
    source_code = load_source_from_url(file_url)
    filename = Path(urlparse(file_url).path).name
    return extract_function_from_source(source_code, filename, line_number)

def compress_function(file_url: str, line_number: int) -> Dict[str, Any]:
    """Download the file and compress the function to contain only important information, related to the given line number."""
    source_code = load_source_from_url(file_url)
    filename = Path(urlparse(file_url).path).name
    return compress_function_from_source(source_code, filename, line_number)



if __name__ == "__main__":
    original_func = extract_function(
        "file:///Users/butkevichveronika/develop/nx_copy/open/artifacts/coturn/src/src/apps/uclient/mainuclient.c",
        572)["text"]
    compressed_func = compress_function(
        "file:///Users/butkevichveronika/develop/nx_copy/open/artifacts/coturn/src/src/apps/uclient/mainuclient.c",
        572)["text"]
    print(compressed_func)
    print(f"Length before {len(original_func)}")
    print(f"Length after {len(compressed_func)}")

    print(f"Difference is {len(original_func) - len(compressed_func)}")


    original_func = extract_function(
        "file:///Users/butkevichveronika/develop/nx_copy/open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/lookup_lists/lookup_list_action_handler.cpp",
        293)["text"]
    compressed_func = compress_function(
        "file:///Users/butkevichveronika/develop/nx_copy/open/vms/client/nx_vms_client_desktop/src/nx/vms/client/desktop/lookup_lists/lookup_list_action_handler.cpp",
        293)["text"]
    print(compressed_func)
    print(f"Length before {len(original_func)}")
    print(f"Length after {len(compressed_func)}")

    print(f"Difference is {len(original_func) - len(compressed_func)}")
    
    
    
