from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from anki_know import load_anki
from config import Config
from hsk import load_hsk, select_hsk
from meta_analysis import run_meta_analysis


def main() -> None:
    cfg = Config.load("config.json")
    run_meta_analysis(cfg, select_hsk(load_hsk(cfg.hsk_data_dir), cfg.hsk_version), load_anki(cfg))


if __name__ == "__main__":
    main()
