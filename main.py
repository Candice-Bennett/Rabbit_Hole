from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from anki_know import AnkiKnowledge, export_missing, print_anki
from ankiconnect_client import AnkiConnectClient
from chart import bars
from config import Config
from console import fatal
from difficulty import analyse as analyse_difficulty, print_difficulty
from hsk import load_hsk
from ingest import load_text
from text_cleaning import clean_text
from word_analysis import WordAnalysisService


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
    force_words = hsk["2.0"].all_words() | hsk["3.1"].all_words()

    analysis = WordAnalysisService(
        force_words, cfg.segment_batch_size, cfg.example_sentence_min_hanzi, cfg.example_sentence_max_hanzi
    )
    candidates = analysis.analyse(text)
    print(f"Found {len(candidates)} unique words, {sum(c.count for c in candidates)} words total")

    for hsk_list in hsk.values():
        d = analyse_difficulty(candidates, hsk_list)
        print_difficulty(d)
        levels = [(l.level, l.unique) for l in d.levels] + [("unknown", d.unknown_unique)]
        tokens = [(l.level, l.tokens) for l in d.levels] + [("unknown", d.unknown_tokens)]
        bars(f"{d.name} - unique words", levels)
        bars(f"{d.name} - total count", tokens)

    if not cfg.anki_fields:
        return

    client = AnkiConnectClient(cfg.ankiconnect_url)
    knowledge = AnkiKnowledge(client, cfg.anki_fields, cfg.mature_interval_days, cfg.ankiconnect_timeout)
    if not knowledge.available:
        return

    stats = knowledge.classify(candidates)
    print_anki(stats)

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
