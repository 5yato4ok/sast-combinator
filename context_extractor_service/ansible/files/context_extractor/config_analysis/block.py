from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .shared import _try_parse_config
from ..ts_utils import line_range, node_text


KeyExtractor = Callable[[Any, bytes], str]


def extract_config_block(
    source: str, filepath: Path, line_number: int,
) -> dict[str, Any]:
    """
    Extract the logical config block containing *line_number*.

    Works via tree-sitter for YAML, Dockerfile, HCL, TOML, JSON.
    Returns ``{block_text, block_type, key_path, start_line, end_line}``.
    """
    tree, lang_key, src_bytes = _try_parse_config(source, filepath)
    if not tree or not src_bytes:
        return _extract_block_text_fallback(source, line_number)

    target = _find_deepest_node_at_line(tree.root_node, line_number)
    if not target:
        return _extract_block_text_fallback(source, line_number)
    if tree.root_node.has_error and _node_or_ancestors_include_error(target):
        raise ValueError(f"Failed to parse config file: {filepath}")

    block = _find_block_ancestor(target, lang_key)
    s, e = line_range(block)
    block_text = node_text(block, src_bytes)
    key_path = _build_key_path(block, lang_key, src_bytes)

    return {
        "block_text": block_text,
        "block_type": block.type,
        "key_path": key_path,
        "start_line": s + 1,
        "end_line": e + 1,
        "language": lang_key,
    }


def _node_or_ancestors_include_error(node) -> bool:
    current = node
    while current is not None:
        if current.type == "ERROR":
            return True
        current = current.parent
    return False


def _find_deepest_node_at_line(node, line_number: int):
    """Find the deepest AST node that contains *line_number* (1-based).

    When multiple children cover the same line (e.g. a newline node and
    an instruction node), prefer the one that *starts* on the target line
    so that whitespace/newline nodes don't shadow real content.

    Iterative implementation to avoid RecursionError on deeply nested configs.
    """
    s = node.start_point[0] + 1
    e = node.end_point[0] + 1
    if not (s <= line_number <= e):
        return None

    current = node
    while True:
        best_child = None
        for ch in current.children:
            cs = ch.start_point[0] + 1
            ce = ch.end_point[0] + 1
            if not (cs <= line_number <= ce):
                continue
            # Prefer children that start on the target line
            if cs == line_number:
                best_child = ch
                break
            if best_child is None:
                best_child = ch
        if best_child is None:
            return current
        current = best_child


_BLOCK_TYPES: dict[str, set[str]] = {
    "yaml": {
        "block_mapping_pair", "block_mapping", "block_sequence",
        "flow_mapping", "document",
    },
    "dockerfile": {
        "run_instruction", "copy_instruction", "add_instruction",
        "env_instruction", "expose_instruction", "from_instruction",
        "cmd_instruction", "entrypoint_instruction", "arg_instruction",
        "label_instruction", "volume_instruction", "user_instruction",
        "workdir_instruction", "healthcheck_instruction",
    },
    "hcl": {
        "block", "attribute", "object",
    },
    "toml": {
        "table", "pair", "array",
    },
    "json": {
        "pair", "object", "array",
    },
    "bash": {
        "command", "if_statement", "for_statement", "function_definition",
        "pipeline", "variable_assignment",
    },
    "python": {
        "expression_statement", "assignment", "import_statement",
        "import_from_statement", "function_definition", "class_definition",
        "if_statement", "for_statement", "with_statement",
    },
}


def _find_block_ancestor(node, lang_key: str):
    """Walk up the AST to find the nearest meaningful block node."""
    types = _BLOCK_TYPES.get(lang_key, set())
    if node.type in types:
        return node
    current = node
    while current.parent:
        if current.type in types:
            return current
        current = current.parent
    if current == node and types:
        line = node.start_point[0]
        for ch in current.children:
            if ch.type in types and ch.start_point[0] <= line <= ch.end_point[0]:
                return ch
    return node


def _build_key_path(node, lang_key: str, src_bytes: bytes) -> str:
    """Build a dotted key path from root to *node* for YAML/TOML/JSON/HCL."""
    parts: list[str] = []
    current = node
    while current.parent:
        key = _extract_key_from_node(current, lang_key, src_bytes)
        if key:
            parts.append(key)
        current = current.parent
    parts.reverse()
    return ".".join(parts)


def _strip_wrapped_quotes(text: str) -> str:
    return text.strip().strip('"').strip("'")


def _extract_yaml_key(node, src_bytes: bytes) -> str:
    if node.type != "block_mapping_pair":
        return ""
    for child in node.children:
        if child.type == "flow_node" or child.type.endswith("_scalar"):
            return _strip_wrapped_quotes(node_text(child, src_bytes))
    return ""


def _extract_pair_key(node, src_bytes: bytes) -> str:
    if node.type != "pair":
        return ""
    for child in node.children:
        if child.type in {"bare_key", "string", "property_identifier"}:
            return _strip_wrapped_quotes(node_text(child, src_bytes))
    return ""


def _extract_hcl_key(node, src_bytes: bytes) -> str:
    if node.type not in {"block", "attribute"}:
        return ""
    for child in node.children:
        if child.type in {"identifier", "string_lit"}:
            return _strip_wrapped_quotes(node_text(child, src_bytes))
    return ""


def _extract_dockerfile_key(node, _src_bytes: bytes) -> str:
    return node.type.replace("_instruction", "").upper()


_KEY_EXTRACTORS: dict[str, KeyExtractor] = {
    "yaml": _extract_yaml_key,
    "toml": _extract_pair_key,
    "json": _extract_pair_key,
    "hcl": _extract_hcl_key,
    "dockerfile": _extract_dockerfile_key,
}


def _extract_key_from_node(node, lang_key: str, src_bytes: bytes) -> str:
    """Extract the key name from a mapping pair / attribute / etc."""
    extractor = _KEY_EXTRACTORS.get(lang_key)
    if extractor is None:
        return ""
    return extractor(node, src_bytes)


def _extract_block_text_fallback(
    source: str, line_number: int,
) -> dict[str, Any]:
    """Fallback: extract lines at the same or deeper indentation level."""
    lines = source.splitlines()
    if line_number < 1 or line_number > len(lines):
        return {"block_text": "", "block_type": "unknown", "key_path": "",
                "start_line": line_number, "end_line": line_number}

    idx = line_number - 1
    target_indent = len(lines[idx]) - len(lines[idx].lstrip())

    # Expand upward to find block start
    start = idx
    while start > 0:
        prev = lines[start - 1]
        if not prev.strip() or prev.strip().startswith("#"):
            start -= 1
            continue
        prev_indent = len(prev) - len(prev.lstrip())
        if prev_indent < target_indent:
            break
        start -= 1

    # Expand downward
    end = idx
    while end < len(lines) - 1:
        nxt = lines[end + 1]
        if not nxt.strip() or nxt.strip().startswith("#"):
            end += 1
            continue
        nxt_indent = len(nxt) - len(nxt.lstrip())
        if nxt_indent < target_indent:
            break
        end += 1

    block_text = "\n".join(lines[start:end + 1])
    return {
        "block_text": block_text,
        "block_type": "indented_block",
        "key_path": "",
        "start_line": start + 1,
        "end_line": end + 1,
    }
