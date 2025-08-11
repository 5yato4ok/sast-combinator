from __future__ import annotations
from typing import Optional
from .config import COMMENT_STYLE

def compute_comment_lines(lang_key: str, lines: list[str]) -> set[int]:
    """Mark indices of comment-only lines (line comments and block comment spans)."""
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
                    for beg, end in block_delims:
                        k = s.find(beg, j)
                        if k != -1 and (idx_open == -1 or k < idx_open):
                            idx_open = k
                            end_tok = end
                    if idx_open == -1:
                        break
                    in_block = True
                    comment_lines.add(i)
                    j = idx_open + len(end_tok)  # move past opener (len mismatch not critical here)
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
            if s.lstrip().startswith(line_prefixes):
                comment_lines.add(i)

    return comment_lines

def first_inline_comment_index(line: str, lang_key: str) -> Optional[int]:
    style = COMMENT_STYLE.get(lang_key, {"line": [], "block": []})
    tokens = list(style.get("line", [])) + [beg for (beg, _end) in style.get("block", [])]
    best = None
    for tok in tokens:
        k = line.find(tok)
        if k != -1 and any(ch not in " \t" for ch in line[:k]):
            best = k if best is None else min(best, k)
    return best

def mask_code_keep_comment(line: str, lang_key: str) -> Optional[str]:
    idx = first_inline_comment_index(line, lang_key)
    if idx is None:
        return None
    # keep indentation
    i = 0
    while i < len(line) and line[i] in (" ", "\t"):
        i += 1
    return f"{line[:i]}… {line[idx:].rstrip()}"
