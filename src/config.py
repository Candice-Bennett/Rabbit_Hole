from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from console import warn


@dataclass
class AnkiField:
    note_type: str
    field_name: str


@dataclass
class Config:

    # Meta-analysis
    meta_analysis: bool = False
    opening_words: int = 20000
    ranking_hsk_version: str = "3.1"
    reading_path_tolerance: float = 2.0
    reading_path_length_weight: float = 0.1

    # Already known
    seen_times_to_count_as_learned: int = 10
    use_read_books: bool = False
    read_books_knowledge: str = "seen_times"
    read_books_percentage_understood: float | list = 95.0
    anki_analysis: bool = False
    mature_interval_days: int = 21
    anki_fields: list[AnkiField] = field(default_factory=list)

    # Files
    input_path: str = ""
    hsk_data_dir: str = "hsk_data"
    missing_words_output: str = ""
    run_for_all_files_in_data: bool = False
    only_run_epub: bool = False
    only_run_txt: bool = False

    # Plot properties
    use_chapters: bool = True
    chart_bucket_words: int = 5000
    occurrence_bands: list[int] = field(default_factory=lambda: [1, 5, 10, 15, 20])
    occurrence_overflow_band: bool = True
    coverage_targets: list = field(default_factory=lambda: [95, 98])
    chengyu_analysis: bool = False
    chart_width_px: int = 1650
    chart_height_px: int = 1050
    chart_x_limits: list = field(default_factory=lambda: [None, None])
    chart_y_limits: dict = field(default_factory=dict)

    # Example sentences
    example_sentence_min_hanzi: int = 6
    example_sentence_max_hanzi: int = 20

    # Debug
    segment_batch_size: int = 32
    parallel_segmenting: bool = False
    background_charts: bool = True
    clean_text: bool = True
    clear_author_notes: bool = True
    exclude_names: bool = False
    ankiconnect_url: str = "http://127.0.0.1:8765"
    ankiconnect_timeout: int = 30

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            raw = {k: v for k, v in raw.items() if v != ""}
            raw_fields = raw.pop("anki_fields", [])
            anki_fields = [AnkiField(**d) for d in raw_fields]
            return cls(anki_fields=anki_fields, **raw)
        except FileNotFoundError:
            warn(f"Config: couldn't find {str(path)!r}, using default settings")
        except (json.JSONDecodeError, TypeError) as e:
            warn(f"Config: {str(path)!r} is malformed ({e}), using default settings")
        return cls()
