from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from anki_know import BUCKETS, LABELS, AnkiKnowledge, export_missing
from ankiconnect_client import AnkiConnectClient
from chart import (
    ANKI_COLOURS,
    ChartSettings,
    hsk_colours,
    plot_breakdown,
    plot_coverage,
    plot_new_over_time,
    plot_occurrences,
    plot_read_so_far,
    plot_seen_so_far,
    plot_text_lengths,
)
from config import Config
from console import fatal, warn
from hsk import HskList, load_hsk
from ingest import load_text
from models import WordCandidate
from new_over_time import (
    Groups,
    category_breakdown,
    characters_in,
    chengyu_in,
    coverage,
    group_words,
    is_chengyu,
    new_over_time,
    occurrences,
    seen_so_far,
    text_lengths,
    word_itself,
)
from sectioning import split_chapters
from text_cleaning import clean_text
from word_analysis import WordAnalysisService

UNITS = {"characters": characters_in, "hanzi": characters_in, "words": word_itself, "chengyu": chengyu_in}
NOT_IN_HSK = "Not in HSK"


@dataclass
class Run:
    groups: Groups
    stem: str
    settings: ChartSettings
    bands: list[int]
    overflow: bool
    learned_after: int

    def path(self, name: str, note: str = "") -> Path:
        path = Path("output") / f"{self.stem}_{name}.png"
        print(f"Wrote {str(path)!r}{note}")
        return path


@dataclass
class ChartSet:
    new_nouns: list[str]
    nouns: list[str]
    prefix: str


def chart_new(run: Run, noun: str, known: set[str] | None = None) -> None:
    data = new_over_time(run.groups, UNITS[noun], known)
    anki = "" if known is None else "anki_"
    note = "" if known is None else f" ({len(known)} {noun} known in Anki)"
    path = run.path(f"{anki}unique_new_{noun}", note)
    plot_new_over_time(data, noun, path, run.groups, run.settings, excluding_known=known is not None)


def chart_suite(run: Run, nouns: list[str], prefix: str, known: dict[str, set[str]] | None = None) -> None:
    anki = "anki_" if known else ""
    known = known or {}
    excluding_known = bool(known)

    def per_noun(calc, *args) -> list:
        return [(n, calc(run.groups, UNITS[n], *args, known.get(n))) for n in nouns]

    def target(name: str) -> tuple[str, Path, Groups, ChartSettings]:
        return f"{prefix}{name}", run.path(f"{anki}{prefix}{name}"), run.groups, run.settings

    occ = per_noun(occurrences, run.bands)
    for as_ratio in (False, True):
        name = "occurrences_ratio" if as_ratio else "occurrences"
        plot_occurrences(occ, *target(name), as_ratio, excluding_known, run.overflow)
    plot_read_so_far(occ, *target("cumulative_read"), excluding_known=excluding_known)
    plot_seen_so_far(per_noun(seen_so_far, run.bands), *target("cumulative_unique_seen"), excluding_known=excluding_known)
    if known or run.learned_after:
        plot_coverage(per_noun(coverage, run.learned_after), *target("coverage"), run.learned_after, excluding_known)


def chart_sets(run: Run, sets: list[ChartSet], known: dict[str, set[str]] | None = None) -> None:
    for chart_set in sets:
        for noun in chart_set.new_nouns:
            chart_new(run, noun, None if known is None else known[noun])
        chart_suite(run, chart_set.nouns, chart_set.prefix, known)


def chart_hsk(run: Run, key: str, hsk_list: HskList) -> None:
    categories = [f"HSK {level}" for level in hsk_list.levels] + [NOT_IN_HSK]

    def category_of(word: str) -> str:
        level = hsk_list.level_of(word)
        return f"HSK {level}" if level else NOT_IN_HSK

    chart = f"hsk{key}_levels"
    data = category_breakdown(run.groups, categories, category_of)
    colours = hsk_colours(len(hsk_list.levels))
    plot_breakdown(data, f"{hsk_list.name} level", colours, chart, run.path(chart), run.groups, run.settings)


def chart_anki_knowledge(run: Run, knowledge: AnkiKnowledge) -> None:
    categories = [LABELS[b] for b in BUCKETS]
    colours = [ANKI_COLOURS[b] for b in BUCKETS]
    data = category_breakdown(run.groups, categories, lambda w: LABELS[knowledge.bucket(w)])
    path = run.path("anki_knowledge")
    plot_breakdown(data, "Anki status", colours, "anki_knowledge", path, run.groups, run.settings)


def has_chengyu(candidates: list[WordCandidate]) -> bool:
    return any(is_chengyu(c.text) for c in candidates)


def main(input_name: str | None = None) -> None:
    cfg = Config.load("config.json")
    input_path = cfg.input_path or (Path("data") / input_name if input_name else None)
    if not input_path:
        fatal("Usage: python main.py <filename in data/> (or set input_path in config.json)")

    try:
        text = load_text(str(input_path))
    except FileNotFoundError:
        fatal(f"Couldn't find input file {str(input_path)!r}, check the filename (or input_path in config.json)")

    if cfg.clean_text:
        before = len(text)
        text = clean_text(text)
        print(f"Cleaned text: {before} chars, now {len(text)} chars")

    hsk = load_hsk(cfg.hsk_data_dir)
    force_words = set().union(*(hsk_list.all_words() for hsk_list in hsk.values()))

    service = WordAnalysisService(
        force_words,
        cfg.segment_batch_size,
        cfg.example_sentence_min_hanzi,
        cfg.example_sentence_max_hanzi,
        cfg.exclude_names,
    )
    analysis = service.analyse(split_chapters(text))
    candidates = analysis.candidates
    print(f"Found {len(candidates)} unique words, {sum(c.count for c in candidates)} words total")

    run = Run(
        group_words(analysis.words_by_chapter, cfg.use_chapters, cfg.chart_bucket_words),
        Path(input_path).stem,
        ChartSettings(cfg.chart_width_px, cfg.chart_height_px, cfg.chart_x_limits, cfg.chart_y_limits, cfg.coverage_targets),
        sorted({b for b in cfg.occurrence_bands if b > 0}) or [1],
        cfg.occurrence_overflow_band,
        max(cfg.seen_times_to_count_as_learned, 0),
    )
    sets = [ChartSet(["characters", "words"], ["words", "hanzi"], "")]
    if cfg.chengyu_analysis and has_chengyu(candidates):
        sets.append(ChartSet(["chengyu"], ["chengyu"], "chengyu_"))

    print()
    chart_sets(run, sets)
    for key, hsk_list in hsk.items():
        chart_hsk(run, key, hsk_list)
    plot_text_lengths(text_lengths(analysis.sentences, run.groups), run.path("text_lengths"), run.groups, run.settings)

    if not cfg.anki_analysis:
        return
    if not cfg.anki_fields:
        warn("Anki: anki_analysis is on but anki_fields is empty, skipping the Anki check")
        return

    client = AnkiConnectClient(cfg.ankiconnect_url)
    knowledge = AnkiKnowledge(client, cfg.anki_fields, cfg.mature_interval_days, cfg.ankiconnect_timeout)
    if not knowledge.available:
        return

    known_words = knowledge.known_words()
    known_characters = knowledge.known_characters()
    known = {
        "characters": known_characters,
        "hanzi": known_characters,
        "words": known_words,
        "chengyu": {w for w in known_words if is_chengyu(w)},
    }
    print()
    chart_anki_knowledge(run, knowledge)
    chart_sets(run, sets, known)

    missing = knowledge.missing(candidates)
    if not missing:
        return
    answer = input(f"\nExport the {len(missing)} missing words to a file? (y/n): ").strip().lower()
    if answer == "y":
        out = cfg.missing_words_output or "output/missing_words.txt"
        export_missing(missing, out)
        print(f"Wrote {out!r}, {len(missing)} words")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
