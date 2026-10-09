from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from console import warn

SUMMARY_FILE = "summary.json"


@dataclass
class BookSummary:
    name: str
    source: str
    chapters: int
    exclude_names: bool
    sentence_hanzi: float
    paragraph_hanzi: float
    opening_words: int
    counts: dict[str, int]
    opening_counts: dict[str, int]
    examples: dict[str, str] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def build_summary(
    name: str,
    source: str,
    words_by_chapter: list[list[str]],
    sentence_hanzi: float,
    paragraph_hanzi: float,
    opening_words: int,
    exclude_names: bool,
    examples: dict[str, str] | None = None,
) -> BookSummary:
    words = [w for chapter in words_by_chapter for w in chapter]
    return BookSummary(
        name,
        source,
        len(words_by_chapter),
        exclude_names,
        sentence_hanzi,
        paragraph_hanzi,
        opening_words,
        dict(Counter(words).most_common()),
        dict(Counter(words[:opening_words]).most_common()),
        examples or {},
    )


def save_summary(summary: BookSummary, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / SUMMARY_FILE
    path.write_text(json.dumps(asdict(summary), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_summaries(output_dir: Path) -> list[BookSummary]:
    summaries = []
    for path in sorted(output_dir.glob(f"*/{SUMMARY_FILE}")):
        try:
            summaries.append(BookSummary(**json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, TypeError) as e:
            warn(f"Meta-analysis: {str(path)!r} is malformed ({e}), skipping it, re-run main.py on that book")
    return summaries
