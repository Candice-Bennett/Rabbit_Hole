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
class DifficultyLevel:
    name: str
    min_known: float | None = None
    max_unknown_words: int | None = None
    max_unique_words: int | None = None


def default_levels() -> list[DifficultyLevel]:
    return [
        DifficultyLevel("Intermediate 中级", 80, 1900, 3400),
        DifficultyLevel("Upper intermediate 中高级", 80, 2800, 4550),
        DifficultyLevel("Advanced 高级", 78, 3300, 5000),
        DifficultyLevel("Master 精通"),
    ]


@dataclass
class Config:

    # Meta-analysis
    meta_analysis: bool = False
    opening_words: int = 20000
    hsk_version: str = "all"
    reading_path_tolerance: float = 2.0
    reading_path_length_weight: float = 0.1
    repetition_times: int = 10
    words_to_learn: int = 500
    difficulty_levels: list[DifficultyLevel] = field(default_factory=default_levels)

    # Already known
    seen_times_to_count_as_learned: int = 25
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
    run_for_data_files: bool = False
    only_run_for_missing_files: bool = False
    only_run_epub: bool = False
    only_run_txt: bool = False

    # Plot properties
    use_chapters: bool = True
    chart_bucket_words: int = 5000
    occurrence_bands: list[int] = field(default_factory=lambda: [1, 5, 10, 15, 20, 25])
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
    parallel_segmenting: bool = True
    background_charts: bool = True
    clean_text: bool = True
    clear_author_notes: bool = True
    exclude_names: bool = True
    ankiconnect_url: str = "http://127.0.0.1:8765"
    ankiconnect_timeout: int = 30

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            raw = {k: v for k, v in raw.items() if v != ""}
            raw_fields = raw.pop("anki_fields", [])
            anki_fields = [AnkiField(**d) for d in raw_fields]
            if "difficulty_levels" in raw:
                raw["difficulty_levels"] = [DifficultyLevel(**d) for d in raw["difficulty_levels"]]
            return cls(anki_fields=anki_fields, **raw)
        except FileNotFoundError:
            warn(f"Config: couldn't find {str(path)!r}, using default settings")
        except (json.JSONDecodeError, TypeError) as e:
            warn(f"Config: {str(path)!r} is malformed ({e}), using default settings")
        return cls()
