from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urldefrag

EPUB_HOUSEKEEPING_FILES = {"nav.xhtml", "toc.xhtml", "message.xhtml", "info.xhtml", "index.xhtml"}
DOWNLOADER_SIGNATURE = re.compile(r"novel-downloader|小说下载器")
HR_TAG = re.compile(r"<hr\s*/?>", re.IGNORECASE)
BODY_TAG = re.compile(r"<body[^>]*>", re.IGNORECASE)
CHAPTER_BREAK = ""
FILE_BREAK = ""
MIN_TOC_BREAKS = 2


class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip_depth = 0
        self.chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data):
        if not self.skip_depth:
            self.chunks.append(data)


def html_to_text(html: str) -> str:
    parser = HTMLTextExtractor()
    parser.feed(html)
    return "\n".join(parser.chunks)


def strip_epub(html: str) -> str:
    matches = list(HR_TAG.finditer(html))
    if not matches:
        return html
    return html[: matches[-1].start()]


def load_text(path: str) -> str:
    p = Path(path)
    if p.suffix.lower() == ".epub":
        return load_epub(p)
    return p.read_text(encoding="utf-8")


def flatten_toc(toc) -> list:
    entries = []
    for entry in toc:
        if isinstance(entry, (tuple, list)):
            entries.extend(flatten_toc(entry))
        else:
            entries.append(entry)
    return entries


def toc_targets(book) -> dict[str, set[str]]:
    targets: dict[str, set[str]] = {}
    for entry in flatten_toc(book.toc):
        href = getattr(entry, "href", None)
        if not href:
            continue
        name, anchor = urldefrag(unquote(href))
        targets.setdefault(name, set()).add(anchor)
    return targets


def anchor_position(html: str, anchor: str) -> int | None:
    if not anchor:
        body = BODY_TAG.search(html)
        return body.end() if body else 0
    match = re.search(rf"""\s(?:id|name)\s*=\s*["']{re.escape(anchor)}["']""", html)
    if not match:
        return None
    return html.rfind("<", 0, match.start())


def mark_chapters(html: str, anchors: set[str]) -> tuple[str, int]:
    positions = sorted({p for p in (anchor_position(html, a) for a in anchors) if p is not None and p >= 0})
    for p in reversed(positions):
        html = f"{html[:p]}\n{CHAPTER_BREAK}\n{html[p:]}"
    return html, len(positions)


def load_epub(path: Path) -> str:
    import ebooklib
    from ebooklib import epub

    book = epub.read_epub(str(path))
    spine = [book.get_item_with_id(item_id) for item_id, _ in book.spine]
    items = [item for item in spine if item is not None and item.get_type() == ebooklib.ITEM_DOCUMENT]
    raw_by_name = {item.file_name: item.get_content().decode("utf-8", errors="ignore") for item in items}

    downloader_signature = any(DOWNLOADER_SIGNATURE.search(html) for html in raw_by_name.values())
    targets = toc_targets(book)
    targets_by_basename = {PurePosixPath(name).name: anchors for name, anchors in targets.items()}

    parts = []
    breaks = 0
    for item in items:
        if Path(item.file_name).name.lower() in EPUB_HOUSEKEEPING_FILES:
            continue
        html = raw_by_name[item.file_name]
        if downloader_signature:
            html = strip_epub(html)
        anchors = targets.get(item.file_name) or targets_by_basename.get(PurePosixPath(item.file_name).name, set())
        html, marked = mark_chapters(html, anchors)
        breaks += marked
        parts.append(html_to_text(html))
    text = f"\n\n{FILE_BREAK}\n\n".join(parts)
    if breaks < MIN_TOC_BREAKS:
        text = text.replace(CHAPTER_BREAK, "")
    return text
