from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

HSK2_LEVELS = ["1", "2", "3", "4", "5", "6"]
HSK3_LEVELS = ["1", "2", "3", "4", "5", "6", "7-9"]


@dataclass
class HskList:
    name: str
    levels: list[str]
    word_level: dict[str, str] = field(default_factory=dict)

    def level_of(self, word: str) -> str | None:
        return self.word_level.get(word)

    def all_words(self) -> set[str]:
        return set(self.word_level)


def _load_words(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load(folder: Path, prefix: str, name: str, levels: list[str]) -> HskList:
    hsk = HskList(name=name, levels=levels)
    for level in levels:
        for word in _load_words(folder / f"{prefix}_words_level{level}.txt"):
            hsk.word_level.setdefault(word, level)
    return hsk


def load_hsk(base_dir: str = "hsk_data") -> dict[str, HskList]:
    base = Path(base_dir)
    return {
        "2.0": _load(base / "HSK2.0", "HSK2.0", "HSK 2.0", HSK2_LEVELS),
        "3.1": _load(base / "HSK3.1", "HSK3.1", "HSK 3.1", HSK3_LEVELS),
    }
