from __future__ import annotations

import re

HAS_HANZI = re.compile(r"[一-鿿]")


def hanzi_count(text: str) -> int:
    return len(HAS_HANZI.findall(text))
