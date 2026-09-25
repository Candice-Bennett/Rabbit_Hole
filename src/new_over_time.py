from __future__ import annotations

from bisect import bisect_left
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import accumulate

from console import warn
from models import Sentence
from word_analysis import HAS_HANZI, hanzi_count

Units = Callable[[str], Iterable[str]]


@dataclass
class Groups:
    by_chapter: bool
    positions: list[int]
    words: list[list[str]]
    bucket_words: int


def transpose(rows: list[list]) -> list[list]:
    return [list(column) for column in zip(*rows)]


def running(rows: list[list[int]]) -> list[list[int]]:
    return [list(accumulate(column)) for column in zip(*rows)]


@dataclass
class NewOverTime:
    new: list[int]

    @property
    def cumulative(self) -> list[int]:
        return list(accumulate(self.new))


@dataclass
class Occurrences:
    bands: list[int]
    counts: list[list[int]]
    lengths: list[int]

    def band_values(self, as_ratio: bool, overflow: bool = True) -> list[list[float]]:
        kept = len(self.bands) + 1 if overflow else len(self.bands)
        return transpose(
            [
                [c / length if length else 0.0 for c in row[:kept]] if as_ratio else row[:kept]
                for row, length in zip(self.counts, self.lengths)
            ]
        )

    def cumulative_band_values(self) -> list[list[int]]:
        return running(self.counts)


@dataclass
class SeenSoFar:
    bands: list[int]
    counts: list[list[int]]

    def band_values(self) -> list[list[int]]:
        return transpose(self.counts)


@dataclass
class Coverage:
    shares: list[float]
    overall: float


@dataclass
class CategoryBreakdown:
    categories: list[str]
    read: list[list[int]]
    unique: list[list[int]]

    def shares(self) -> list[list[float]]:
        return transpose([[c / sum(row) if sum(row) else 0.0 for c in row] for row in self.read])

    def cumulative_read(self) -> list[list[int]]:
        return running(self.read)

    def cumulative_unique(self) -> list[list[int]]:
        return running(self.unique)


@dataclass
class TextLengths:
    sentence: list[float]
    paragraph: list[float]
    overall_sentence: float
    overall_paragraph: float


def characters_in(word: str) -> Iterable[str]:
    return (c for c in word if HAS_HANZI.match(c))


def word_itself(word: str) -> Iterable[str]:
    return (word,)


def is_chengyu(word: str) -> bool:
    return hanzi_count(word) >= 4


def chengyu_in(word: str) -> Iterable[str]:
    return (word,) if is_chengyu(word) else ()


def group_words(words_by_chapter: list[list[str]], use_chapters: bool, bucket_words: int) -> Groups:
    if use_chapters and len(words_by_chapter) > 1:
        return Groups(True, list(range(1, len(words_by_chapter) + 1)), words_by_chapter, bucket_words)
    if use_chapters:
        warn("Charts: couldn't find any chapter breaks, grouping by word count instead")
    words = [w for chapter in words_by_chapter for w in chapter]
    starts = range(0, len(words), bucket_words)
    positions = [min(start + bucket_words, len(words)) for start in starts]
    return Groups(False, positions, [words[start : start + bucket_words] for start in starts], bucket_words)


def new_over_time(groups: Groups, units: Units, known: set[str] | None = None) -> NewOverTime:
    seen: set[str] = set(known or ())
    new = []
    for words in groups.words:
        found = {u for w in words for u in units(w)}
        new.append(len(found - seen))
        seen |= found
    return NewOverTime(new)


def occurrences(groups: Groups, units: Units, bands: list[int], known: set[str] | None = None) -> Occurrences:
    known = known or set()
    seen: Counter = Counter()
    counts = []
    lengths = []
    for words in groups.words:
        row = [0] * (len(bands) + 1)
        length = 0
        for w in words:
            for u in units(w):
                length += 1
                if u in known:
                    continue
                seen[u] += 1
                row[bisect_left(bands, seen[u])] += 1
        counts.append(row)
        lengths.append(length)
    return Occurrences(bands, counts, lengths)


def seen_so_far(groups: Groups, units: Units, bands: list[int], known: set[str] | None = None) -> SeenSoFar:
    known = known or set()
    seen: Counter = Counter()
    counts = []
    for words in groups.words:
        seen.update(u for w in words for u in units(w) if u not in known)
        row = [0] * (len(bands) + 1)
        for times in seen.values():
            row[bisect_left(bands, times)] += 1
        counts.append(row)
    return SeenSoFar(bands, counts)


def coverage(groups: Groups, units: Units, learned_after: int, known: set[str] | None = None) -> Coverage:
    known = known or set()
    seen: Counter = Counter()
    shares = []
    known_total = total = 0
    for words in groups.words:
        known_here = length = 0
        for w in words:
            for u in units(w):
                length += 1
                if u in known or (learned_after and seen[u] >= learned_after):
                    known_here += 1
                seen[u] += 1
        shares.append(known_here / length if length else float("nan"))
        known_total += known_here
        total += length
    return Coverage(shares, known_total / total if total else 0.0)


def category_breakdown(groups: Groups, categories: list[str], category_of: Callable[[str], str]) -> CategoryBreakdown:
    index = {c: i for i, c in enumerate(categories)}
    seen: set[str] = set()
    read = []
    unique = []
    for words in groups.words:
        read_row = [0] * len(categories)
        unique_row = [0] * len(categories)
        for w in words:
            i = index[category_of(w)]
            read_row[i] += 1
            if w not in seen:
                seen.add(w)
                unique_row[i] += 1
        read.append(read_row)
        unique.append(unique_row)
    return CategoryBreakdown(categories, read, unique)


def average(total: int, count: int) -> float:
    return total / count if count else float("nan")


def text_lengths(sentences: list[Sentence], groups: Groups) -> TextLengths:
    count = max(len(groups.positions), 1)
    sentence_totals = [0] * count
    sentence_counts = [0] * count
    paragraph_hanzi: dict[int, int] = {}
    paragraph_group: dict[int, int] = {}
    read = 0
    for s in sentences:
        group = s.chapter if groups.by_chapter else min(read // groups.bucket_words, count - 1)
        read += len(s.words)
        hanzi = hanzi_count(s.text)
        if hanzi:
            sentence_totals[group] += hanzi
            sentence_counts[group] += 1
        paragraph_group.setdefault(s.paragraph, group)
        paragraph_hanzi[s.paragraph] = paragraph_hanzi.get(s.paragraph, 0) + hanzi

    paragraph_totals = [0] * count
    paragraph_counts = [0] * count
    for paragraph, hanzi in paragraph_hanzi.items():
        if hanzi:
            paragraph_totals[paragraph_group[paragraph]] += hanzi
            paragraph_counts[paragraph_group[paragraph]] += 1

    return TextLengths(
        [average(t, c) for t, c in zip(sentence_totals, sentence_counts)],
        [average(t, c) for t, c in zip(paragraph_totals, paragraph_counts)],
        average(sum(sentence_totals), sum(sentence_counts)),
        average(sum(paragraph_totals), sum(paragraph_counts)),
    )
