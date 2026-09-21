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

    # Anki
    mature_interval_days: int = 21
    anki_fields: list[AnkiField] = field(default_factory=list)

    # Paths
    input_path: str = ""
    hsk_data_dir: str = "hsk_data"
    missing_words_output: str = ""

    # Example sentnce
    example_sentence_min_hanzi: int = 6
    example_sentence_max_hanzi: int = 20

    # Debug
    segment_batch_size: int = 32
    clean_text: bool = True
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
