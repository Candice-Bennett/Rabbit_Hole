from __future__ import annotations

import io
import sys
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from anki_know import BUCKETS, LABELS, AnkiKnowledge, export_missing, load_anki
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
from hsk import HskList, load_hsk, select_hsk
from ingest import load_text
from meta_analysis import run_meta_analysis
from models import WordCandidate
from read_books import READ_OUTPUT, ReadKnowledge, needs_summary, read_book_files, read_books_knowledge
from new_over_time import (
    Groups,
    TextLengths,
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
from summary import build_summary, save_summary
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
        path = Path("output") / self.stem / f"{name}.png"
        print(f"Wrote {str(path)!r}{note}")
        return path


@dataclass
class ChartSet:
    new_nouns: list[str]
    nouns: list[str]
    prefix: str


def chart_new(run: Run, noun: str, known: set[str] | None = None) -> None:
    data = new_over_time(run.groups, UNITS[noun], known)
    anki = "" if known is None else run.settings.known_prefix
    note = "" if known is None else f" ({len(known)} {noun} {run.settings.known_label})"
    path = run.path(f"{anki}unique_new_{noun}", note)
    plot_new_over_time(data, noun, path, run.groups, run.settings, excluding_known=known is not None)


def chart_suite(run: Run, nouns: list[str], prefix: str, known: dict[str, set[str]] | None = None) -> None:
    anki = run.settings.known_prefix if known else ""
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


def chart_anki_knowledge(run: Run, buckets: dict[str, str]) -> None:
    used = [b for b in BUCKETS if b != "read" or "read" in buckets.values()]
    categories = [LABELS[b] for b in used]
    colours = [ANKI_COLOURS[b] for b in used]
    data = category_breakdown(run.groups, categories, lambda w: LABELS[buckets[w]])
    path = run.path("anki_knowledge")
    plot_breakdown(data, "Anki status", colours, "anki_knowledge", path, run.groups, run.settings)


@dataclass
class AnkiCharts:
    known: dict[str, set[str]]
    buckets: dict[str, str] | None


def draw_charts(run: Run, sets: list[ChartSet], hsk: dict[str, HskList], lengths: TextLengths, anki: AnkiCharts | None) -> str:
    out = io.StringIO()
    with redirect_stdout(out):
        print()
        chart_sets(run, sets)
        for key, hsk_list in hsk.items():
            chart_hsk(run, key, hsk_list)
        plot_text_lengths(lengths, run.path("text_lengths"), run.groups, run.settings)
        if anki is not None:
            print()
            if anki.buckets is not None:
                chart_anki_knowledge(run, anki.buckets)
            chart_sets(run, sets, anki.known)
    return out.getvalue()


class ChartQueue:
    def __init__(self, background: bool, batch: bool):
        self.pool = ProcessPoolExecutor(1) if background else None
        self.batch = batch
        self.pending: tuple[str, Future] | None = None
        self.failed: list[str] = []

    def draw(self, name: str, *args) -> None:
        self.wait()
        if self.pool is None:
            self.report(name, lambda: draw_charts(*args))
        else:
            self.pending = (name, self.pool.submit(draw_charts, *args))

    def wait(self) -> None:
        if self.pending is None:
            return
        name, future = self.pending
        self.pending = None
        print(f"\nCharts for {name}:", end="")
        self.report(name, future.result)

    def report(self, name: str, output: Callable[[], str]) -> None:
        try:
            print(output(), end="")
        except Exception as e:
            if not self.batch:
                raise
            warn(f"Charts failed for {name!r}: {e!r}, moving on")
            self.failed.append(name)

    def close(self) -> None:
        self.wait()
        if self.pool is not None:
            self.pool.shutdown()


def has_chengyu(candidates: list[WordCandidate]) -> bool:
    return any(is_chengyu(c.text) for c in candidates)


def known_labels(knowledge: AnkiKnowledge | None, read: ReadKnowledge) -> tuple[str, str, str]:
    # Chart wording and file prefix for the known-word charts: label, title source, file prefix
    if knowledge is None:
        return "known from books you've read", "Books you've read", "read_"
    if read.known:
        return "known in Anki or from books you've read", "Anki", "anki_"
    return "known in Anki", "Anki", "anki_"


def book_text(input_path: Path, cfg: Config) -> str:
    text = load_text(str(input_path))
    if cfg.clean_text:
        before = len(text)
        text = clean_text(text, cfg.clear_author_notes)
        print(f"Cleaned text: {before} chars, now {len(text)} chars")
    return text


def summarise_read_book(input_path: Path, cfg: Config, service: WordAnalysisService) -> None:
    # Books you've read only need a summary for what they've taught you, no charts or export
    analysis = service.analyse(split_chapters(book_text(input_path, cfg)))
    groups = group_words(analysis.words_by_chapter, cfg.use_chapters, cfg.chart_bucket_words)
    lengths = text_lengths(analysis.sentences, groups)
    summary = build_summary(
        input_path.stem,
        input_path.name,
        analysis.words_by_chapter,
        lengths.overall_sentence,
        lengths.overall_paragraph,
        cfg.opening_words,
        cfg.exclude_names,
    )
    print(f"Wrote {str(save_summary(summary, READ_OUTPUT / input_path.stem))!r}")


def read_books_to_summarise(cfg: Config) -> list[Path]:
    if not cfg.use_read_books:
        return []
    paths: dict[str, Path] = {}
    for path in read_book_files(data_suffixes(cfg)):
        paths.setdefault(path.stem, path)
    return [p for p in paths.values() if needs_summary(p, cfg.exclude_names)]


def analyse_book(
    input_path: Path,
    cfg: Config,
    hsk: dict[str, HskList],
    service: WordAnalysisService,
    knowledge: AnkiKnowledge | None,
    read: ReadKnowledge,
    charts: ChartQueue,
    batch: bool,
) -> None:
    analysis = service.analyse(split_chapters(book_text(input_path, cfg)))
    candidates = analysis.candidates
    print(f"Found {len(candidates)} unique words, {sum(c.count for c in candidates)} words total")

    run = Run(
        group_words(analysis.words_by_chapter, cfg.use_chapters, cfg.chart_bucket_words),
        Path(input_path).stem,
        ChartSettings(
            cfg.chart_width_px,
            cfg.chart_height_px,
            cfg.chart_x_limits,
            cfg.chart_y_limits,
            cfg.coverage_targets,
            *known_labels(knowledge, read),
        ),
        sorted({b for b in cfg.occurrence_bands if b > 0}) or [1],
        cfg.occurrence_overflow_band,
        max(cfg.seen_times_to_count_as_learned, 0),
    )
    sets = [ChartSet(["characters", "words"], ["words", "hanzi"], "")]
    if cfg.chengyu_analysis and has_chengyu(candidates):
        sets.append(ChartSet(["chengyu"], ["chengyu"], "chengyu_"))

    lengths = text_lengths(analysis.sentences, run.groups)
    summary = build_summary(
        run.stem,
        input_path.name,
        analysis.words_by_chapter,
        lengths.overall_sentence,
        lengths.overall_paragraph,
        cfg.opening_words,
        cfg.exclude_names,
    )
    print(f"Wrote {str(save_summary(summary, Path('output') / run.stem))!r} (for rank.py)")

    # Only the plain charts without Anki or books you've read, otherwise one known-word set
    # on top that counts everything you know from either
    if knowledge is None and not read.known:
        charts.draw(input_path.name, run, sets, hsk, lengths, None)
        return

    known_words = read.known | (knowledge.known_words() if knowledge else set())
    known_characters = read.characters | (knowledge.known_characters() if knowledge else set())
    known = {
        "characters": known_characters,
        "hanzi": known_characters,
        "words": known_words,
        "chengyu": {w for w in known_words if is_chengyu(w)},
    }
    if knowledge is None:
        charts.draw(input_path.name, run, sets, hsk, lengths, AnkiCharts(known, None))
        return

    buckets = {c.text: knowledge.bucket(c.text) for c in candidates}
    buckets.update({w: "read" for w, b in buckets.items() if b != "know_well" and w in read.known})
    charts.draw(input_path.name, run, sets, hsk, lengths, AnkiCharts(known, buckets))

    missing = [c for c in knowledge.missing(candidates) if c.text not in read.known]
    if not missing:
        return
    book_out = str(Path("output") / run.stem / "missing_words.txt")
    if batch:
        out = book_out
    else:
        answer = input(f"\nExport the {len(missing)} missing words to a file? (y/n): ").strip().lower()
        if answer != "y":
            return
        out = cfg.missing_words_output or book_out
    export_missing(missing, out)
    print(f"Wrote {out!r}, {len(missing)} words")


def data_suffixes(cfg: Config) -> set[str]:
    if cfg.only_run_epub and not cfg.only_run_txt:
        return {".epub"}
    if cfg.only_run_txt and not cfg.only_run_epub:
        return {".txt"}
    return {".epub", ".txt"}


def find_inputs(cfg: Config, input_name: str | None) -> list[Path]:
    if input_name:
        return [Path("data") / input_name]
    if cfg.input_path:
        return [Path(cfg.input_path)]
    if not cfg.run_for_data_files:
        fatal("run_for_data_files is off, so pass a filename: python main.py <filename in data/>")
    suffixes = data_suffixes(cfg)
    inputs = sorted(p for p in Path("data").iterdir() if p.is_file() and p.suffix.lower() in suffixes)
    if not inputs:
        fatal(f"No {'/'.join(sorted(suffixes))} files found in data/")
    if cfg.only_run_for_missing_files:
        inputs = [p for p in inputs if not (Path("output") / p.stem).is_dir()]
        if not inputs:
            fatal("Every book in data/ already has an output folder, run rank.py to re-rank them", 0)
    return inputs


def main(input_name: str | None = None) -> None:
    cfg = Config.load("config.json")
    inputs = find_inputs(cfg, input_name)
    batch = len(inputs) > 1

    for path in inputs:
        if not path.is_file():
            fatal(f"Couldn't find input file {str(path)!r}, check the filename (or input_path in config.json)")

    all_hsk = load_hsk(cfg.hsk_data_dir)
    force_words = set().union(*(hsk_list.all_words() for hsk_list in all_hsk.values()))
    hsk = select_hsk(all_hsk, cfg.hsk_version)
    service = WordAnalysisService(
        force_words,
        cfg.segment_batch_size,
        cfg.example_sentence_min_hanzi,
        cfg.example_sentence_max_hanzi,
        cfg.exclude_names,
        2 if cfg.parallel_segmenting else 1,
    )
    knowledge = load_anki(cfg)
    charts = ChartQueue(cfg.background_charts, batch)

    failed = []
    try:
        read = read_books_to_summarise(cfg)
        for i, path in enumerate(read, 1):
            print(f"\n=== Book you've read [{i}/{len(read)}] {path.name} ===")
            try:
                summarise_read_book(path, cfg, service)
            except Exception as e:
                warn(f"Failed on {path.name!r}: {e!r}, it won't count towards what you know")
        read_known = read_books_knowledge(cfg)
        for i, path in enumerate(inputs, 1):
            print(f"\n=== [{i}/{len(inputs)}] {path.name} ===")
            try:
                analyse_book(path, cfg, hsk, service, knowledge, read_known, charts, batch)
            except Exception as e:
                if not batch:
                    raise
                warn(f"Failed on {path.name!r}: {e!r}, moving on")
                failed.append(path.name)
        charts.close()
    finally:
        service.close()
    failed += charts.failed

    if batch:
        print(f"\nDone: {len(inputs) - len(failed)}/{len(inputs)} books, charts are in output/<book name>/")
        if failed:
            warn("Failed: " + ", ".join(failed))

    if cfg.meta_analysis:
        run_meta_analysis(cfg, hsk, knowledge, read_known)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
