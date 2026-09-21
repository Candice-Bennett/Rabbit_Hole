from __future__ import annotations

import re

DIVIDER = re.compile(r"^[ \t]*[….]{4,}[ \t]*$", re.MULTILINE)
CREDIT_LINE = re.compile(r"^.*本文件由.*$", re.MULTILINE)
HEADER_LABEL = re.compile(r"^\**(作者|Tag列表|原始网址|封面图片地址|简介|主角|一句话简介|下载时间)\**[：:]")
AUTHOR_NOTE = re.compile(r"作者有话说[：:]?")


def clean_text(text: str) -> str:
    text = strip_header(text)
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
    while True:
        match = AUTHOR_NOTE.search(text)
        if not match:
            return text
        rest = text[match.end():]
        next_divider = DIVIDER.search(rest)
        if next_divider:
            text = text[: match.start()] + rest[next_divider.start():]
        else:
            text = text[: match.start()]
