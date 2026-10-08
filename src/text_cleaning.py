from __future__ import annotations

import re

from ingest import CHAPTER_BREAK, FILE_BREAK

DIVIDER = re.compile(r"^[ \t]*[….]{4,}[ \t]*$", re.MULTILINE)
NUMBER = r"[0-9０-９〇零一二三四五六七八九十百千万两]+"
HEADING = re.compile(
    rf"""^[ \t　]*(?:\#+[ \t]*)?                      # optional markdown '#'
    (?:第[ \t　]*{NUMBER}[ \t　]*[章节回卷部篇集幕话]  # 第一章 / 第 1 章 / 第3节 / 第二卷
     |{NUMBER}[ \t　]*[章回]                          # 1章
     |(?:序章|楔子|引子|尾声|终章)[ \t　]*$)            # unnumbered openers / closers
    (?:[ \t　：:、.·\-]+[^\n。，；]{{0,30}})?[ \t　]*$  # optional short title, no prose punctuation
    """,
    re.MULTILINE | re.VERBOSE,
)
CHAPTER_EDGE = re.compile(rf"{DIVIDER.pattern}|{HEADING.pattern}|[{CHAPTER_BREAK}{FILE_BREAK}]", re.MULTILINE | re.VERBOSE)
CREDIT_LINE = re.compile(r"^.*本文件由.*$", re.MULTILINE)
HEADER_LABEL = re.compile(r"^\**(作者|Tag列表|原始网址|封面图片地址|简介|主角|一句话简介|下载时间)\**[：:]")
AUTHOR_NOTE = re.compile(r"^[ \t　]*作者有话要?说[：:]?", re.MULTILINE)


def clean_text(text: str, author_notes: bool = True) -> str:
    text = strip_header(text)
    if author_notes:
        text = strip_author_notes(text)
    return text


def strip_header(text: str) -> str:
    credit_match = CREDIT_LINE.search(text[:4000])
    if credit_match:
        return skip_blank_lines(text[credit_match.end():])

    lines = text.split("\n")
    head = lines[:30]
    label_lines = [i for i, line in enumerate(head) if HEADER_LABEL.match(line.strip())]
    if len(label_lines) >= 2:
        cut_at = max(label_lines) + 1
        return skip_blank_lines("\n".join(lines[cut_at:]))

    return text


def skip_blank_lines(text: str) -> str:
    lines = text.split("\n")
    i = 0
    while i < len(lines) and (lines[i].strip() == "" or DIVIDER.fullmatch(lines[i].strip())):
        i += 1
    return "\n".join(lines[i:])


def strip_author_notes(text: str) -> str:
    kept = []
    pos = 0
    for note in AUTHOR_NOTE.finditer(text):
        if note.start() < pos:
            continue
        kept.append(text[pos : note.start()])
        edge = CHAPTER_EDGE.search(text, note.end())
        pos = edge.start() if edge else len(text)
    kept.append(text[pos:])
    return "".join(kept)
