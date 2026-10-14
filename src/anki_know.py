from __future__ import annotations

import re
from pathlib import Path

import requests

from ankiconnect_client import AnkiConnectClient
from config import AnkiField, Config
from console import warn
from hanzi import HAS_HANZI
from models import WordCandidate

STRIP_HTML = re.compile(r"<[^>]+>")
BATCH_SIZE = 1000

BUCKETS = ("know_well", "read", "learning", "present", "missing")
LABELS = {
    "know_well": "Know well",
    "read": "Known from books you've read",
    "learning": "Already learning",
    "present": "Present, not learned",
    "missing": "Missing",
}


def strip_html(text: str) -> str:
    return STRIP_HTML.sub("", text).strip()


class AnkiKnowledge:
    def __init__(self, client: AnkiConnectClient, fields: list[AnkiField], mature_days: int = 21, timeout: int = 30):
        self.client = client
        self.fields = fields
        self.mature_days = mature_days
        self.timeout = timeout
        self.word_cards: dict[str, list[int]] = {}
        self.card_info: dict[int, dict] = {}
        self.available = self._connect()
        if self.available:
            self.available = self._load()

    def _connect(self) -> bool:
        print(
            "Anki: connecting, may take a while if you have a large collection, "
            "increase ankiconnect_timeout in the config if needed"
        )
        try:
            self.client.invoke("version", timeout=self.timeout)
            return True
        except requests.exceptions.ConnectionError:
            warn(
                "Anki: could not connect to AnkiConnect, skipping the Anki knowledge check.\n"
                "  - Make sure Anki is open\n"
                "  - Make sure the AnkiConnect add-on is installed (code 2055492159) and Anki was restarted after installing it\n"
                f"  - Check that ankiconnect_url in config.json matches AnkiConnect's address (currently {self.client.url!r})"
            )
            return False
        except requests.exceptions.Timeout:
            warn("Anki: AnkiConnect took too long to respond, skipping the Anki knowledge check.")
            return False

    def _batched(self, action: str, key: str, ids: list[int]) -> list[dict]:
        results = []
        for start in range(0, len(ids), BATCH_SIZE):
            results += self.client.invoke(action, {key: ids[start : start + BATCH_SIZE]}, timeout=self.timeout)
        return results

    def _load(self) -> bool:
        try:
            for f in self.fields:
                note_ids = self.client.invoke("findNotes", {"query": f'note:"{f.note_type}"'}, timeout=self.timeout)
                if not note_ids:
                    warn(f"Anki: no notes found for note type {f.note_type!r}, check the spelling in Anki")
                    continue

                actual_fields = self.client.invoke("modelFieldNames", {"modelName": f.note_type}, timeout=self.timeout)
                resolved = f.field_name
                if f.field_name not in actual_fields:
                    match = next((a for a in actual_fields if a.lower() == f.field_name.lower()), None)
                    if not match:
                        warn(f"Anki: field {f.field_name!r} not found on {f.note_type!r} (fields: {actual_fields})")
                        continue
                    warn(f"Anki: field {f.field_name!r} not found on {f.note_type!r}, using {match!r} instead")
                    resolved = match

                for info in self._batched("notesInfo", "notes", note_ids):
                    field_data = info.get("fields", {}).get(resolved)
                    if not field_data or not field_data.get("value"):
                        continue
                    word = strip_html(field_data["value"])
                    self.word_cards.setdefault(word, []).extend(info.get("cards", []))

            all_cards = sorted({cid for cards in self.word_cards.values() for cid in cards})
            if all_cards:
                for info in self._batched("cardsInfo", "cards", all_cards):
                    self.card_info[info["cardId"]] = info
            return True
        except requests.exceptions.RequestException:
            warn("Anki: AnkiConnect stopped responding, skipping the Anki knowledge check.")
            return False

    def bucket(self, word: str) -> str:
        cards = self.word_cards.get(word)
        if not cards:
            return "missing"
        infos = [self.card_info[c] for c in cards if c in self.card_info]
        if any(i["type"] == 2 and i["interval"] >= self.mature_days for i in infos):
            return "know_well"
        if any(i["reps"] > 0 for i in infos):
            return "learning"
        return "present"

    def missing(self, candidates: list[WordCandidate]) -> list[WordCandidate]:
        return [c for c in candidates if self.bucket(c.text) == "missing"]

    def known_words(self) -> set[str]:
        return {w for w in self.word_cards if self.bucket(w) == "know_well"}

    def known_characters(self) -> set[str]:
        return {c for w in self.known_words() for c in w if HAS_HANZI.match(c)}


def load_anki(cfg: Config) -> AnkiKnowledge | None:
    if not cfg.anki_analysis:
        return None
    if not cfg.anki_fields:
        warn("Anki: anki_analysis is on but anki_fields is empty, skipping the Anki check")
        return None
    client = AnkiConnectClient(cfg.ankiconnect_url)
    knowledge = AnkiKnowledge(client, cfg.anki_fields, cfg.mature_interval_days, cfg.ankiconnect_timeout)
    return knowledge if knowledge.available else None


SIGNATURE = "# rabbit-hole export"


def export_missing(words: list[WordCandidate], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{c.text}\t{c.count}\t{c.example}" for c in words]
    Path(path).write_text(SIGNATURE + "\n" + "\n".join(lines), encoding="utf-8")
