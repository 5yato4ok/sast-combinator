"""Removal of known secret values from text bound for a log."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Redactor:
    """Replaces every occurrence of each non-empty secret with ``mask``, longest secret first."""

    secrets: tuple[str, ...]
    mask: str = "***"

    @classmethod
    def of(cls, secrets: Iterable[object], mask: str = "***") -> Redactor:
        values = {str(item) for item in secrets if item}
        return cls(tuple(sorted(values, key=len, reverse=True)), mask)

    def __call__(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, self.mask)
        return text
