from __future__ import annotations

import re

from ingest import CHAPTER_BREAK, FILE_BREAK
from text_cleaning import DIVIDER, HEADING

SENTENCE_END = re.compile(r"[。！？!?」”]")
HANZI = re.compile(r"[一-鿿]")
MIN_HEADINGS = 2
MIN_CHAPTER_HANZI = 50


def split_chapters(text: str) -> list[str]:
    if CHAPTER_BREAK in text:
        return tidy(text.replace(FILE_BREAK, "").split(CHAPTER_BREAK))

    plain = text.replace(FILE_BREAK, "")
    headings = [m.start() for m in HEADING.finditer(plain)]
    dividers = [m.end() for m in DIVIDER.finditer(plain)]
    starts = max(headings, dividers, key=len)
    if len(starts) >= MIN_HEADINGS:
        return tidy(split_at(plain, starts))

    if FILE_BREAK in text:
        return tidy(text.split(FILE_BREAK))
    if starts:
        return tidy(split_at(plain, starts))
    return [text]


def split_at(text: str, starts: list[int]) -> list[str]:
    bounds = [0, *starts, len(text)]
    return [text[a:b] for a, b in zip(bounds, bounds[1:])]


def is_prose(chunk: str) -> bool:
    if len(HANZI.findall(chunk)) < MIN_CHAPTER_HANZI:
        return False
    return bool(SENTENCE_END.search(DIVIDER.sub("", chunk)))


def tidy(chunks: list[str]) -> list[str]:
    chapters: list[str] = []
    pending = ""
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        if not is_prose(chunk):
            pending = f"{pending}\n\n{chunk}" if pending else chunk
            continue
        chapters.append(f"{pending}\n\n{chunk}" if pending else chunk)
        pending = ""
    if pending:
        if chapters:
            chapters[-1] = f"{chapters[-1]}\n\n{pending}"
        else:
            chapters.append(pending)
    return chapters or [""]
