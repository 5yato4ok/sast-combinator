from __future__ import annotations
from typing import List, Tuple
from .config import LANG_NODESETS

def collect_multiline_header(lines: List[str], lang_key: str, f_start: int, f_end: int) -> tuple[list[str], int]:
    """Collect multi-line function signature/header."""
    if LANG_NODESETS[lang_key]["closing_is_brace"]:
        header: list[str] = []
        cursor = f_start
        found = False
        while cursor <= f_end:
            line = lines[cursor]
            header.append(line)
            if "{" in line:
                found = True
                cursor += 1
                break
            cursor += 1
        if not found and cursor <= f_end:
            if cursor <= f_end and lines[cursor].strip() == "{":
                header.append(lines[cursor]); cursor += 1
        return header, cursor
    else:
        return [lines[f_start]], f_start + 1
