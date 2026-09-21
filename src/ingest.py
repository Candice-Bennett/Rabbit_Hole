from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

EPUB_HOUSEKEEPING_FILES = {"nav.xhtml", "toc.xhtml", "message.xhtml", "info.xhtml", "index.xhtml"}
DOWNLOADER_SIGNATURE = re.compile(r"novel-downloader|小说下载器")
HR_TAG = re.compile(r"<hr\s*/?>", re.IGNORECASE)


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


def load_epub(path: Path) -> str:
    import ebooklib
    from ebooklib import epub

    book = epub.read_epub(str(path))
    items = [item for item in book.get_items() if item.get_type() == ebooklib.ITEM_DOCUMENT]
    raw_by_name = {item.file_name: item.get_content().decode("utf-8", errors="ignore") for item in items}

    downloader_signature = any(DOWNLOADER_SIGNATURE.search(html) for html in raw_by_name.values())

    parts = []
    for item in items:
        if Path(item.file_name).name.lower() in EPUB_HOUSEKEEPING_FILES:
            continue
        html = raw_by_name[item.file_name]
        if downloader_signature:
            html = strip_epub(html)
        parts.append(html_to_text(html))
    return "\n\n".join(parts)
