from __future__ import annotations
from typing import List

def dedent_minimum(lines: List[str]) -> List[str]:
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
