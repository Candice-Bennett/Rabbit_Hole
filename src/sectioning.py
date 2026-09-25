from __future__ import annotations

import re

from ingest import CHAPTER_BREAK
from text_cleaning import DIVIDER

CHAPTER = re.compile(r"^第[0-9〇一二三四五六七八九十百千两零]+[章节回].*$", re.MULTILINE)
HANZI = re.compile(r"[一-鿿]")
MIN_HEADINGS = 2
MIN_LEAD_LINES = 2


def split_chapters(text: str) -> list[str]:
    if CHAPTER_BREAK in text:
        return [p.strip() for p in text.split(CHAPTER_BREAK)]

    starts = [m.start() for m in CHAPTER.finditer(text)]
    if len(starts) >= MIN_HEADINGS:
        return split_at(text, starts)

    starts = [m.end() for m in DIVIDER.finditer(text)]
    if starts:
        return split_at(text, starts)

    return [text]


def split_at(text: str, starts: list[int]) -> list[str]:
    bounds = [0, *starts, len(text)]
    lead, *chapters = [text[a:b] for a, b in zip(bounds, bounds[1:])]
    if sum(1 for line in lead.splitlines() if HANZI.search(line)) >= MIN_LEAD_LINES:
        return [lead, *chapters]
    chapters[0] = lead + chapters[0]
    return chapters
