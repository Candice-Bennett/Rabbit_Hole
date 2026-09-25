from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WordCandidate:
    text: str
    count: int
    example: str = ""


@dataclass
class Sentence:
    text: str
    words: list[str]
    chapter: int = 0
    paragraph: int = 0


@dataclass
class TextAnalysis:
    candidates: list[WordCandidate]
    words_by_chapter: list[list[str]]
    sentences: list[Sentence]
