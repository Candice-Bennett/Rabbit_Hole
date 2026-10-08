from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from config import Config
from console import fatal, warn
from hanzi import HAS_HANZI
from summary import SUMMARY_FILE, BookSummary, load_summaries

READ_DIR = Path("data") / "books_read"
READ_OUTPUT = Path("output") / "books_read"
SUFFIXES = {".epub", ".txt"}


def read_book_files(suffixes: set[str] = SUFFIXES) -> list[Path]:
    if not READ_DIR.is_dir():
        return []
    return sorted(p for p in READ_DIR.iterdir() if p.is_file() and p.suffix.lower() in suffixes)


def needs_summary(path: Path, exclude_names: bool) -> bool:
    out = READ_OUTPUT / path.stem / SUMMARY_FILE
    if not out.exists() or out.stat().st_mtime < path.stat().st_mtime:
        return True
    try:
        return json.loads(out.read_text(encoding="utf-8")).get("exclude_names") != exclude_names
    except json.JSONDecodeError:
        return True


def most_common_covering(counts: dict[str, int], share: float) -> set[str]:
    target = share * sum(counts.values())
    known: set[str] = set()
    covered = 0
    for word, count in sorted(counts.items(), key=lambda wc: (-wc[1], wc[0])):
        if covered >= target:
            break
        known.add(word)
        covered += count
    return known


@dataclass
class ReadKnowledge:
    known: set[str] = field(default_factory=set)
    lines: list[str] = field(default_factory=list)

    @property
    def books(self) -> int:
        return len(self.lines)

    @property
    def characters(self) -> set[str]:
        return {c for w in self.known for c in w if HAS_HANZI.match(c)}


def percentages_for(names: list[str], setting: float | list) -> dict[str, float]:
    # One value covers every book, a list is matched to the books in alphabetical order
    values = setting if isinstance(setting, list) else [setting]
    if len(values) == 1:
        return {name: float(values[0]) for name in names}
    if len(values) < len(names):
        fatal(
            f"read_books_percentage_understood has {len(values)} values but data/books_read has "
            f"{len(names)} books. Give one value, or one per book in this order:\n"
            + "\n".join(f"  {i}. {name}" for i, name in enumerate(names, 1))
        )
    if len(values) > len(names):
        warn(
            f"Read books: read_books_percentage_understood has {len(values)} values but only "
            f"{len(names)} books, ignoring the last {len(values) - len(names)}"
        )
    return {name: float(v) for name, v in zip(names, values)}


def known_from(book: BookSummary, mode: str, percentage: float, learned_after: int) -> set[str]:
    if mode == "percentage_understood":
        return most_common_covering(book.counts, percentage / 100)
    return {w for w, c in book.counts.items() if learned_after and c >= learned_after}


def read_books_knowledge(cfg: Config) -> ReadKnowledge:
    if not cfg.use_read_books:
        return ReadKnowledge()
    mode = cfg.read_books_knowledge
    if mode not in ("seen_times", "percentage_understood"):
        warn(
            f"Read books: unknown read_books_knowledge {mode!r} "
            "(use 'seen_times' or 'percentage_understood'), using 'seen_times'"
        )
        mode = "seen_times"
    if mode == "seen_times" and cfg.seen_times_to_count_as_learned <= 0:
        warn("Read books: seen_times_to_count_as_learned is 0, so books you've read add no known words")

    in_folder = sorted({p.stem for p in read_book_files()})
    percentages = percentages_for(in_folder, cfg.read_books_percentage_understood) if mode == "percentage_understood" else {}
    books = sorted((b for b in load_summaries(READ_OUTPUT) if b.name in in_folder), key=lambda b: b.name)
    missing = sorted(set(in_folder) - {b.name for b in books})
    if missing:
        warn(f"Read books: {len(missing)} book(s) in data/books_read have no summary yet, run main.py to include them:")
        for name in missing:
            warn(f"  - {name}")

    read = ReadKnowledge()
    for book in books:
        words = known_from(book, mode, percentages.get(book.name, 0), cfg.seen_times_to_count_as_learned)
        read.known |= words
        how = f"{percentages[book.name]:g}% understood" if mode == "percentage_understood" else (
            f"seen {cfg.seen_times_to_count_as_learned}+ times"
        )
        read.lines.append(f"{book.name}: {len(words):,} words ({how})")
    return read
