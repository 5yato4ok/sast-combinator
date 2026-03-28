from __future__ import annotations

from pathlib import Path

from ..ts_utils import create_parser, detect_language


def _try_parse_config(source: str, filepath: Path):
    try:
        lang, lang_key = detect_language(filepath)
    except ValueError:
        return None, None, None
    parser = create_parser(lang)
    src_bytes = source.encode("utf-8", errors="replace")
    tree = parser.parse(src_bytes)
    return tree, lang_key, src_bytes


def _parse_config_or_none(source: str, filepath: Path):
    tree, lang_key, src_bytes = _try_parse_config(source, filepath)
    if tree is None:
        return None, None, None
    if tree.root_node.has_error:
        raise ValueError(f"Failed to parse config file: {filepath}")
    return tree, lang_key, src_bytes
