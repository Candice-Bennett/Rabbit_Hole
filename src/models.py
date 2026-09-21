from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WordCandidate:
    text: str
    count: int
    example: str = ""
