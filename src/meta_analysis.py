from __future__ import annotations

import csv
import math
import statistics
import textwrap
import unicodedata
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from anki_know import AnkiKnowledge
from config import Config
from console import warn
from hanzi import HAS_HANZI, hanzi_count
from hsk import HskList
from read_books import ReadKnowledge, read_books_knowledge
from summary import BookSummary, load_summaries

OUTPUT = Path("output")
OUT_DIR = OUTPUT / "meta-analysis"
SUFFIXES = {".epub", ".txt"}
LINE_WIDTH = 100
BEAM_WIDTH = 64
PATHS = ("optimised", "adjusted", "whole")


@dataclass
class Settings:
    hsk_lists: list[HskList]
    targets: list[float]
    learned_after: int
    opening_words: int
    known: set[str]
    known_sources: list[str]
    known_lines: list[str]
    tolerance: float
    length_weight: float
    repetition_times: int
    repetition_weight: float

    @property
    def has_known(self) -> bool:
        return bool(self.known_sources)

    @property
    def start(self) -> str:
        if not self.known_sources:
            return "nothing"
        return f"your well-known words ({' & '.join(self.known_sources)})"


@dataclass
class HskFit:
    cumulative: list[float]
    needed: list[int]

    @property
    def key(self) -> tuple[int, float]:
        level = self.needed[-1]
        return level, -self.cumulative[min(level, len(self.cumulative) - 1)]

    @property
    def off(self) -> float:
        return 1 - self.cumulative[-1]


@dataclass
class Repetition:
    share: float
    words: int
    unknown: int


@dataclass
class BookStats:
    book: BookSummary
    hanzi: int
    unique_hanzi: int
    hsk: dict[str, HskFit]
    opening_hsk: dict[str, HskFit]
    opening_new: int
    opening_new_hanzi: int
    chengyu_per_10k: float
    yours: float | None
    yours_opening: float | None
    repetition: Repetition
    opening_repetition: Repetition

    @property
    def short(self) -> bool:
        return self.book.total < self.book.opening_words


@dataclass
class Ranking:
    title: str
    about: str
    key: Callable[[BookStats], Any]
    headers: list[str]
    row: Callable[[BookStats], list[str]]
    composite: str = ""


@dataclass
class PathStep:
    stats: BookStats
    coverage: float
    cold: float
    opening: float
    learned: int
    difficulty: float


def unique_hanzi(counts: dict[str, int]) -> int:
    return len({c for w in counts for c in w if HAS_HANZI.match(c)})


def hsk_fit(counts: dict[str, int], hsk_list: HskList, targets: list[float]) -> HskFit:
    index = {level: i for i, level in enumerate(hsk_list.levels)}
    by_level = [0] * len(hsk_list.levels)
    for word, count in counts.items():
        level = hsk_list.level_of(word)
        if level is not None:
            by_level[index[level]] += count
    total = sum(counts.values()) or 1
    cumulative = []
    covered = 0
    for count in by_level:
        covered += count
        cumulative.append(covered / total)
    needed = [bisect_left(cumulative, t - 1e-9) for t in targets]
    return HskFit(cumulative, needed)


def coverage(counts: dict[str, int], known: set[str], learned_after: int) -> float:
    total = sum(counts.values())
    if not total:
        return 0.0
    unknown = sum(min(c, learned_after) if learned_after else c for w, c in counts.items() if w not in known)
    return 1 - unknown / total


def repetition(counts: dict[str, int], known: set[str], times: int) -> Repetition:
    unknown = {w: c for w, c in counts.items() if w not in known and hanzi_count(w)}
    repeated = {w: c for w, c in unknown.items() if c >= times}
    return Repetition(sum(repeated.values()) / max(sum(unknown.values()), 1), len(repeated), len(unknown))


def book_stats(book: BookSummary, s: Settings) -> BookStats:
    chengyu = sum(c for w, c in book.counts.items() if hanzi_count(w) >= 4)
    yours = coverage(book.counts, s.known, s.learned_after) if s.has_known else None
    yours_opening = coverage(book.opening_counts, s.known, s.learned_after) if s.has_known else None
    return BookStats(
        book,
        sum(hanzi_count(w) * c for w, c in book.counts.items()),
        unique_hanzi(book.counts),
        {h.name: hsk_fit(book.counts, h, s.targets) for h in s.hsk_lists},
        {h.name: hsk_fit(book.opening_counts, h, s.targets) for h in s.hsk_lists},
        len(book.opening_counts),
        unique_hanzi(book.opening_counts),
        chengyu / book.total * 10000 if book.total else 0.0,
        yours,
        yours_opening,
        repetition(book.counts, s.known, s.repetition_times),
        repetition(book.opening_counts, s.known, s.repetition_times),
    )


def judged_on(b: BookStats, adjusted: bool) -> dict[str, int]:
    return b.book.opening_counts if adjusted else b.book.counts


def learned_from(b: BookStats, learned_after: int) -> set[str]:
    return {w for w, c in b.book.counts.items() if learned_after and c >= learned_after}


def length_factors(stats: list[BookStats], weight: float) -> dict[str, float]:
    median = statistics.median(b.book.total for b in stats)
    return {b.book.name: (b.book.total / median) ** weight for b in stats}


def difficulty(b: BookStats, known: set[str], s: Settings, factors: dict[str, float]) -> float:
    # Share of the opening you wouldn't know, nudged up for long books and down for short ones
    return (1 - coverage(b.book.opening_counts, known, s.learned_after)) * factors[b.book.name]


def walk(order: list[BookStats], s: Settings, adjusted: bool, factors: dict[str, float]) -> list[PathStep]:
    known = set(s.known)
    steps = []
    for b in order:
        learned = learned_from(b, s.learned_after) - known
        steps.append(
            PathStep(
                b,
                coverage(b.book.counts, known, s.learned_after),
                coverage(judged_on(b, adjusted), s.known, s.learned_after),
                coverage(b.book.opening_counts, known, s.learned_after),
                len(learned),
                difficulty(b, known, s, factors),
            )
        )
        known |= learned
    return steps


def greedy_order(stats: list[BookStats], s: Settings, adjusted: bool) -> list[BookStats]:
    known = set(s.known)
    remaining = list(stats)
    order = []
    while remaining:
        best = max(remaining, key=lambda b: coverage(judged_on(b, adjusted), known, s.learned_after))
        order.append(best)
        known |= learned_from(best, s.learned_after)
        remaining.remove(best)
    return order


def optimised_order(stats: list[BookStats], s: Settings, factors: dict[str, float]) -> list[BookStats]:
    # Beam search over orders, keeping the BEAM_WIDTH most promising sets of books read so far.
    # What you know only depends on which books you've read, not their order, so each set is
    # scored by the difficulty so far plus the difficulty of every remaining book given what
    # that set has taught you. Only the opening sample affects difficulty, so only its words count.
    # Each pick must be within the tolerance of the best opening coverage on offer, so the word
    # count adjusted path is always one of the orders it can choose.
    words = sorted({w for b in stats for w in b.book.opening_counts})
    index = {w: i for i, w in enumerate(words)}
    n = len(stats)
    plain = np.zeros((n, len(words)))
    learns = np.zeros((n, len(words)), dtype=bool)
    for r, b in enumerate(stats):
        total = max(sum(b.book.opening_counts.values()), 1)
        for w, c in b.book.opening_counts.items():
            plain[r, index[w]] = (min(c, s.learned_after) if s.learned_after else c) / total
        for w in learned_from(b, s.learned_after):
            if w in index:
                learns[r, index[w]] = True
    # plain gives the unknown share of each opening, weighted adds the length adjustment
    weighted = plain * np.array([factors[b.book.name] for b in stats])[:, None]

    beams = [(0.0, (), np.array([w in s.known for w in words]))]
    for _ in range(n):
        children: dict[frozenset, tuple] = {}
        for cost, order, known in beams:
            remaining = np.ones(n, dtype=bool)
            remaining[list(order)] = False
            unknown = (~known).astype(float)
            costs = weighted @ unknown
            # The tolerance is on how much of the opening you'd know, the 'opening' column
            shares = plain @ unknown
            easiest = shares[remaining].min()
            allowed = np.flatnonzero(remaining & (shares <= easiest + max(s.tolerance, 0) + 1e-12))
            rest = weighted[remaining].sum(axis=0)
            after = unknown[None, :] * ~learns[allowed]
            future = ((rest[None, :] - weighted[allowed]) * after).sum(axis=1)
            for r, ahead in zip(allowed, future):
                key = frozenset(order) | {int(r)}
                so_far = cost + costs[r]
                if key not in children or so_far < children[key][1]:
                    children[key] = (so_far + ahead, so_far, order + (int(r),), known | learns[r])
        best = sorted(children.values(), key=lambda c: (c[0], [stats[r].book.name for r in c[2]]))
        beams = [(so_far, order, known) for _, so_far, order, known in best[:BEAM_WIDTH]]
    return [stats[r] for r in min(beams, key=lambda b: b[0])[1]]


def reading_paths(stats: list[BookStats], s: Settings) -> dict[str, list[PathStep]]:
    factors = length_factors(stats, s.length_weight)
    paths = {
        "adjusted": walk(greedy_order(stats, s, True), s, True, factors),
        "whole": walk(greedy_order(stats, s, False), s, False, factors),
    }
    optimised = walk(optimised_order(stats, s, factors), s, True, factors)
    # The search keeps a limited number of candidates, so fall back if the simple path does better
    paths["optimised"] = min(optimised, paths["adjusted"], key=average_difficulty)
    return paths


def average_difficulty(steps: list[PathStep]) -> float:
    return sum(st.difficulty for st in steps) / max(len(steps), 1)


def percentiles(keys: list) -> list[float]:
    ordered = sorted(keys)
    top = max(len(keys) - 1, 1)
    return [(bisect_left(ordered, k) + bisect_right(ordered, k) - 1) / 2 / top for k in keys]


def pct(x: float | None) -> str:
    return "-" if x is None or math.isnan(x) else f"{x * 100:.1f}%"


def num(x: float) -> str:
    return "-" if math.isnan(x) else f"{x:.1f}"


def nan_last(x: float) -> float:
    return math.inf if math.isnan(x) else x


def level_name(hsk_list: HskList, index: int) -> str:
    return f"HSK {hsk_list.levels[index]}" if index < len(hsk_list.levels) else f"past HSK {hsk_list.levels[-1]}"


def short_mark(b: BookStats) -> str:
    return "*" if b.short else ""


def vocab_ranking(s: Settings, hsk_list: HskList, targets: list[str]) -> Ranking:
    name = hsk_list.name
    return Ranking(
        f"Vocabulary level ({name})",
        f"The {name} level you'd need to know every word in to cover {' / '.join(targets)} of the text, "
        f"then the share of the text covered by each level and below. Books that need the same level are "
        f"ordered by how much of the text that level covers, so books 'past HSK' are ordered by how much "
        f"of the text is in {name} at all.",
        lambda b: b.hsk[name].key,
        [f"{t} needs" for t in targets] + [f"<=HSK {lv}" for lv in hsk_list.levels],
        lambda b: [level_name(hsk_list, i) for i in b.hsk[name].needed] + [pct(c) for c in b.hsk[name].cumulative],
        "vocab",
    )


def opening_ranking(s: Settings, hsk_list: HskList, targets: list[str]) -> Ranking:
    name = hsk_list.name
    return Ranking(
        f"Opening difficulty ({name}, first {s.opening_words:,} words)",
        f"The {name} level you'd need to know every word in to cover {' / '.join(targets)} of the first "
        f"{s.opening_words:,} words, then the share of those words that are in {name} at all. The vocabulary "
        "level lists below do the same for the whole book. "
        + ("Your coverage is shown for reference, but the order is by HSK. " if s.has_known else "")
        + "\n* = book is shorter than the sample, so this is the whole book.",
        lambda b: b.opening_hsk[name].key,
        [f"{t} needs" for t in targets]
        + [f"all {name}"]
        + (["your coverage"] if s.has_known else []),
        lambda b: [level_name(hsk_list, i) + short_mark(b) for i in b.opening_hsk[name].needed]
        + [pct(b.opening_hsk[name].cumulative[-1])]
        + ([pct(b.yours_opening)] if s.has_known else []),
        "opening",
    )


def rankings(s: Settings) -> list[Ranking]:
    targets = [f"{t * 100:g}%" for t in s.targets]
    opening = f"{s.opening_words:,}"
    unknown = "words you don't know yet" if s.has_known else "words in the book"
    each = "word you don't know yet" if s.has_known else "word"

    def opening_density(b: BookStats) -> float:
        return b.opening_new / max(min(b.book.total, s.opening_words), 1)

    lists = [
        Ranking(
            "Repetition",
            f"How often the {unknown} come back. A word counts as repeated once it's used "
            f"{s.repetition_times} or more times.\n"
            f"- share: each time you come across a {each}, the chance it's a repeated word. e.g. 40% "
            f"means 4 in every 10 are words that come up at least {s.repetition_times} times, so you get "
            "plenty of practice with them.\n"
            f"- words: how many different words are repeated, out of all the different {unknown}.\n"
            f"Ordered by share in the first {opening} words, highest (easiest) first. The whole book columns "
            "favour longer books, so they're for reference only and don't count towards the overall score.\n"
            "* = book is shorter than the sample, so this is the whole book.",
            lambda b: (-b.opening_repetition.share,),
            [f"share, first {opening}", f"words, first {opening}", "share, whole book", "words, whole book"],
            lambda b: [
                pct(b.opening_repetition.share) + short_mark(b),
                f"{b.opening_repetition.words:,} of {b.opening_repetition.unknown:,}",
                pct(b.repetition.share),
                f"{b.repetition.words:,} of {b.repetition.unknown:,}",
            ],
            "repetition",
        ),
        Ranking(
            "New-word density",
            f"Unique words and hanzi, and unique words per 1,000 words, in the first {opening} words "
            f"and in the whole book. Ordered by the first {opening} words, so long books aren't "
            "penalised for being long.\n"
            "* = book is shorter than the sample, so it looks easier than it is.",
            lambda b: (opening_density(b),),
            [
                f"words, first {opening}",
                f"hanzi, first {opening}",
                f"per 1k, first {opening}",
                "words, whole book",
                "hanzi, whole book",
                "per 1k, whole book",
            ],
            lambda b: [
                f"{b.opening_new:,}{short_mark(b)}",
                f"{b.opening_new_hanzi:,}",
                f"{opening_density(b) * 1000:.0f}",
                f"{len(b.book.counts):,}",
                f"{b.unique_hanzi:,}",
                f"{len(b.book.counts) / max(b.book.total, 1) * 1000:.0f}",
            ],
            "density",
        ),
        Ranking(
            "Sentence length",
            "Average hanzi per sentence and per paragraph.",
            lambda b: (nan_last(b.book.sentence_hanzi), nan_last(b.book.paragraph_hanzi)),
            ["sentence", "paragraph"],
            lambda b: [num(b.book.sentence_hanzi), num(b.book.paragraph_hanzi)],
            "sentences",
        ),
        Ranking(
            "Chengyu density",
            "Words of 4+ hanzi per 10,000 words",
            lambda b: (b.chengyu_per_10k,),
            ["per 10k words"],
            lambda b: [f"{b.chengyu_per_10k:.1f}"],
        ),
        Ranking(
            "Length",
            "Total words, hanzi and chapters, and the average words and hanzi per chapter.",
            lambda b: (b.book.total,),
            ["words", "hanzi", "chapters", "avg words/chapter", "avg hanzi/chapter"],
            lambda b: [
                f"{b.book.total:,}",
                f"{b.hanzi:,}",
                f"{b.book.chapters:,}",
                f"{b.book.total / max(b.book.chapters, 1):,.0f}",
                f"{b.hanzi / max(b.book.chapters, 1):,.0f}",
            ],
        ),
        Ranking(
            "Vocabulary breadth",
            "Unique words and hanzi in the whole book. Note that longer books naturally have more.",
            lambda b: (len(b.book.counts), b.unique_hanzi),
            ["unique words", "unique hanzi"],
            lambda b: [f"{len(b.book.counts):,}", f"{b.unique_hanzi:,}"],
        ),
        *(opening_ranking(s, h, targets) for h in s.hsk_lists),
        *(vocab_ranking(s, h, targets) for h in s.hsk_lists),
    ]
    if s.has_known:
        lists.insert(
            0,
            Ranking(
                "For you",
                f"Share of the text you already know: {s.start}, plus any word once you've seen it "
                f"{s.learned_after} times in the book. Ordered by the first {opening} words, so every "
                "book is judged on the same amount of text. Longer books repeat their words more, so "
                "they score higher over the whole book.\n"
                "* = book is shorter than the sample.",
                lambda b: (-b.yours_opening, -b.yours),
                [f"first {opening}", "whole book"],
                lambda b: [pct(b.yours_opening) + short_mark(b), pct(b.yours)],
                "for you",
            ),
        )
    return lists


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [max(display_width(c) for c in column) for column in zip(headers, *rows)]

    def line(cells: list[str]) -> str:
        out = []
        for i, (cell, width) in enumerate(zip(cells, widths)):
            gap = " " * (width - display_width(cell))
            out.append(cell + gap if i == 1 else gap + cell)
        return "  ".join(out).rstrip()

    return "\n".join([line(headers), "  ".join("-" * w for w in widths), *(line(r) for r in rows)])


def section(title: str, about: str, body: str) -> str:
    wrapped = "\n".join(textwrap.fill(line, LINE_WIDTH) for line in about.split("\n"))
    return f"{title}\n{'=' * display_width(title)}\n{wrapped}\n\n{body}\n"


def ranked(stats: list[BookStats], key: Callable[[BookStats], Any]) -> list[BookStats]:
    return sorted(stats, key=lambda b: (key(b), b.book.name))


def composites(lists: list[Ranking]) -> list[str]:
    return list(dict.fromkeys(r.composite for r in lists if r.composite))


def composite_scores(stats: list[BookStats], lists: list[Ranking]) -> dict[str, dict[str, float]]:
    scores: dict[str, dict[str, float]] = {b.book.name: {} for b in stats}
    for composite in composites(lists):
        shared = [r for r in lists if r.composite == composite]
        for r in shared:
            for b, p in zip(stats, percentiles([r.key(b) for b in stats])):
                scores[b.book.name][composite] = scores[b.book.name].get(composite, 0.0) + p / len(shared)
    return scores


def composite_weight(composite: str, s: Settings) -> float:
    return max(s.repetition_weight, 0) if composite == "repetition" else 1.0


def overall_score(book_scores: dict[str, float], s: Settings) -> float:
    total = sum(composite_weight(c, s) for c in book_scores)
    return sum(p * composite_weight(c, s) for c, p in book_scores.items()) / max(total, 1e-9)


def composite_positions(stats: list[BookStats], scores: dict[str, dict[str, float]], composite: str) -> dict[str, int]:
    order = sorted(stats, key=lambda b: (scores[b.book.name][composite], b.book.name))
    return {b.book.name: i for i, b in enumerate(order, 1)}


def settings_text(s: Settings, books: int) -> str:
    lines = [
        f"Books ranked: {books}",
        f"HSK list{'s' if len(s.hsk_lists) > 1 else ''}: {', '.join(h.name for h in s.hsk_lists)}",
        f"Opening sample: first {s.opening_words:,} words",
        f"A word counts as learned after being seen {s.learned_after} times"
        if s.learned_after
        else "Learning from reading is off (seen_times_to_count_as_learned is 0)",
        *(s.known_lines or ["Known words: no Anki or books you've read, so nothing starts as known"]),
    ]
    return "\n".join(lines)


def path_section(steps: list[PathStep], s: Settings, kind: str) -> str:
    rows = [
        [
            str(i),
            st.stats.book.name,
            pct(st.opening) + short_mark(st.stats),
            pct(st.coverage),
            pct(st.cold),
            f"{st.learned:,}",
            pct(st.difficulty),
        ]
        for i, st in enumerate(steps, 1)
    ]
    start = s.start
    opening = f"first {s.opening_words:,} words"
    judged = "whole text" if kind == "whole" else opening
    titles = {"optimised": "optimised", "adjusted": "word count adjusted", "whole": "whole book"}
    how = {
        "optimised": f"Starts from {start} and searches for the order with the lowest average "
        "difficulty, so it will take a slightly harder book early if what it teaches makes the "
        f"books after it easier. It never picks a book more than {s.tolerance * 100:g} points "
        "harder than the easiest unread book at that point (reading_path_tolerance).",
        "adjusted": f"Starts from {start} and picks the unread book whose {opening} you'd know "
        "the most of. Every book is judged on the same amount of text, so long books don't win "
        "just by repeating their vocabulary more.",
        "whole": f"Starts from {start} and picks the unread book whose whole text you'd know the "
        "most of. Longer books repeat their words more, so they tend to come first here partly "
        "just for being long.",
    }
    return section(
        f"Suggested reading path ({titles[kind]})",
        f"{how[kind]} Every word seen {s.learned_after}+ times in a book counts as learned for the "
        "books after it. 'opening' and 'whole book' are how much you'd know when you reach that "
        f"book if you follow the order, 'cold' is how much of its {judged} you'd know reading it "
        "first. 'picked up' is how many words that book teaches you for the books after it. "
        f"'difficulty' is the share of its {opening} you wouldn't know when you reach it, weighted "
        "slightly so longer books count as a little harder (reading_path_length_weight)."
        + ("" if s.learned_after else " Learning from reading is off, so this is just a coverage ranking.")
        + "\n* = book is shorter than the sample.",
        table(["#", "book", "opening", "whole book", "cold", "picked up", "difficulty"], rows)
        + f"\n\nAverage difficulty along this path: {pct(average_difficulty(steps))}",
    )


def reading_order_text(
    stats: list[BookStats], lists: list[Ranking], paths: dict[str, list[PathStep]], s: Settings
) -> str:
    scores = composite_scores(stats, lists)
    parts = [settings_text(s, len(stats)) + "\n"]
    parts += [path_section(paths[kind], s, kind) for kind in PATHS]

    used = composites(lists)
    overall = sorted(stats, key=lambda b: (overall_score(scores[b.book.name], s), b.book.name))
    positions = {c: composite_positions(stats, scores, c) for c in used}
    overall_rows = [
        [
            str(i),
            b.book.name,
            f"{overall_score(scores[b.book.name], s) * 100:.0f}",
            *(str(positions[c][b.book.name]) for c in used),
            str(sum(positions[c][b.book.name] for c in used)),
        ]
        for i, b in enumerate(overall, 1)
    ]
    parts.append(
        section(
            "Overall difficulty",
            "Average of each book's percentile in the "
            + ", ".join(used)
            + " lists (see difficulty_lists.txt). 0 = easiest in every list, 100 = hardest in every list. "
            + ("The vocab and opening percentiles are each averaged across the HSK lists first. " if len(s.hsk_lists) > 1 else "")
            + (f"Repetition counts {s.repetition_weight:g}x as much as each other list (repetition_weight). " if s.repetition_weight != 1 else "")
            + "Length and breadth are left out because a longer book isn't harder per page. The columns on "
            "the right are the book's position in each list, and 'total' is those positions added up. ",
            table(["#", "book", "score", *used, "total"], overall_rows),
        )
    )
    return "\n".join(parts)


def difficulty_lists_text(stats: list[BookStats], lists: list[Ranking], s: Settings) -> str:
    parts = [settings_text(s, len(stats)) + "\nEvery list is easiest first.\n"]
    for r in lists:
        rows = [[str(i), b.book.name, *r.row(b)] for i, b in enumerate(ranked(stats, r.key), 1)]
        parts.append(section(r.title, r.about, table(["#", "book", *r.headers], rows)))
    return "\n".join(parts)


def write_csv(
    path: Path, stats: list[BookStats], lists: list[Ranking], paths: dict[str, list[PathStep]], s: Settings
) -> None:
    scores = composite_scores(stats, lists)
    positions = {kind: {st.stats.book.name: i for i, st in enumerate(paths[kind], 1)} for kind in PATHS}
    targets = [f"{t * 100:g}" for t in s.targets]

    def prefix(h: HskList) -> str:
        return h.name.replace(" ", "").lower() + "_" if len(s.hsk_lists) > 1 else ""

    def hsk_headers(h: HskList) -> list[str]:
        return (
            [f"{prefix(h)}needs_for_{t}" for t in targets]
            + [f"{prefix(h)}covered_by_hsk_{lv}" for lv in h.levels]
            + [f"{prefix(h)}opening_needs_for_{t}" for t in targets]
        )

    def hsk_cells(b: BookStats, h: HskList) -> list:
        return (
            [level_name(h, i) for i in b.hsk[h.name].needed]
            + [round(c, 4) for c in b.hsk[h.name].cumulative]
            + [level_name(h, i) for i in b.opening_hsk[h.name].needed]
        )

    headers = (
        ["book", "source", "path_position_optimised", "path_position_word_count_adjusted"]
        + ["path_position_whole_book", "overall_score"]
        + ["words", "hanzi", "chapters", "unique_words", "unique_hanzi"]
        + [c for h in s.hsk_lists for c in hsk_headers(h)]
        + ["opening_unique_words", "opening_unique_hanzi", "sentence_hanzi", "paragraph_hanzi", "chengyu_per_10k"]
        + ["your_coverage", "your_opening_coverage"]
        + ["repetition_share", "repeated_words", "opening_repetition_share", "opening_repeated_words"]
    )
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for b in sorted(stats, key=lambda b: positions["optimised"][b.book.name]):
            writer.writerow(
                [b.book.name, b.book.source, *(positions[kind][b.book.name] for kind in PATHS)]
                + [round(overall_score(scores[b.book.name], s) * 100, 1)]
                + [b.book.total, b.hanzi, b.book.chapters, len(b.book.counts), b.unique_hanzi]
                + [c for h in s.hsk_lists for c in hsk_cells(b, h)]
                + [b.opening_new, b.opening_new_hanzi]
                + [round(b.book.sentence_hanzi, 2), round(b.book.paragraph_hanzi, 2), round(b.chengyu_per_10k, 2)]
                + ["" if b.yours is None else round(b.yours, 4)]
                + ["" if b.yours_opening is None else round(b.yours_opening, 4)]
                + [round(b.repetition.share, 4), b.repetition.words]
                + [round(b.opening_repetition.share, 4), b.opening_repetition.words]
            )


def write_meta_analysis(books: list[BookSummary], s: Settings, out_dir: Path) -> list[Path]:
    stats = [book_stats(b, s) for b in books if b.total]
    lists = rankings(s)
    orders = reading_paths(stats, s)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = [out_dir / "reading_order.txt", out_dir / "difficulty_lists.txt", out_dir / "books.csv"]
    paths[0].write_text(reading_order_text(stats, lists, orders, s), encoding="utf-8")
    paths[1].write_text(difficulty_lists_text(stats, lists, s), encoding="utf-8")
    write_csv(paths[2], stats, lists, orders, s)
    return paths


def warn_unsummarised(names: set[str]) -> None:
    data = Path("data")
    if not data.is_dir():
        return
    missing = sorted({p.stem for p in data.iterdir() if p.suffix.lower() in SUFFIXES} - names)
    if missing:
        warn(f"Meta-analysis: {len(missing)} book(s) in data/ have no summary yet, run main.py on them to include them:")
        for name in missing:
            warn(f"  - {name}")


def run_meta_analysis(
    cfg: Config, hsk: dict[str, HskList], knowledge: AnkiKnowledge | None, read: ReadKnowledge | None = None
) -> None:
    books = load_summaries(OUTPUT)
    if not books:
        warn("Meta-analysis: no book summaries in output/ yet, run main.py on your books first")
        return
    warn_unsummarised({b.name for b in books})
    if len({b.exclude_names for b in books}) > 1:
        warn("Meta-analysis: some books were run with exclude_names on and some off, so their numbers aren't comparable")
    stale = sorted(b.name for b in books if b.opening_words != cfg.opening_words)
    if stale:
        warn(f"Meta-analysis: {len(stale)} book(s) were analysed with a different opening_words, run main.py on them again so their opening sample is {cfg.opening_words:,} words:")
        for name in stale:
            warn(f"  - {name}")

    anki_known = knowledge.known_words() if knowledge else set()
    read = read if read is not None else read_books_knowledge(cfg)
    sources, lines = [], []
    if knowledge is not None:
        sources.append("Anki")
        lines.append(f"Anki: {len(anki_known):,} well-known words")
    if read.books:
        sources.append("read books")
        lines.append(f"Books you've read: {read.books}, giving {len(read.known):,} known words")
        lines += [f"  - {line}" for line in read.lines]
    if sources:
        lines.append(f"Known words in total: {len(anki_known | read.known):,}")
    read_known = read.known

    settings = Settings(
        list(hsk.values()),
        sorted(t / 100 for t in cfg.coverage_targets) or [0.98],
        max(cfg.seen_times_to_count_as_learned, 0),
        cfg.opening_words,
        anki_known | read_known,
        sources,
        lines,
        cfg.reading_path_tolerance / 100,
        cfg.reading_path_length_weight,
        max(cfg.repetition_times, 1),
        cfg.repetition_weight,
    )
    print(f"\nRanking {len(books)} books...")
    for path in write_meta_analysis(books, settings, OUT_DIR):
        print(f"Wrote {str(path)!r}")
