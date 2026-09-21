from __future__ import annotations

import re
from collections import Counter

import hanlp

from console import fatal
from models import WordCandidate
from progress import tqdm

HAS_HANZI = re.compile(r"[一-鿿]")


def hanzi_count(text: str) -> int:
    return len(HAS_HANZI.findall(text))


class WordAnalysisService:
    def __init__(
        self,
        force_words: set[str] | None = None,
        segment_batch_size: int = 32,
        example_sentence_min_hanzi: int = 6,
        example_sentence_max_hanzi: int = 20,
    ):
        self.segment_batch_size = segment_batch_size
        self.example_sentence_min_hanzi = example_sentence_min_hanzi
        self.example_sentence_max_hanzi = example_sentence_max_hanzi
        print("Loading HanLP tokenizer (first run downloads the model, this can take a minute)...")
        try:
            self.tokenizer = hanlp.load(hanlp.pretrained.tok.COARSE_ELECTRA_SMALL_ZH)
        except Exception as e:
            fatal(
                f"Couldn't load the HanLP tokenizer ({e})\n"
                "  - This downloads a model on first run, so make sure you're online\n"
                "  - After a successful run it's cached in ~/.hanlp and no longer needs the internet"
            )
        if force_words:
            self.tokenizer.dict_force = force_words

    def analyse(self, text: str) -> list[WordCandidate]:
        sentences = [s.strip() for s in hanlp.utils.rules.split_sentence(text) if s.strip()]

        counts: Counter = Counter()
        examples: dict[str, str] = {}
        first_seen: dict[str, str] = {}

        batches = range(0, len(sentences), self.segment_batch_size)
        for start in tqdm(batches, desc="segmenting", unit="batch"):
            batch = sentences[start : start + self.segment_batch_size]
            for sentence, words in zip(batch, self.tokenizer(batch)):
                usable = self.example_sentence_min_hanzi <= hanzi_count(sentence) <= self.example_sentence_max_hanzi
                for word in words:
                    if not HAS_HANZI.search(word):
                        continue
                    counts[word] += 1
                    if word not in first_seen:
                        first_seen[word] = sentence
                    if usable and word not in examples:
                        examples[word] = sentence

        return [WordCandidate(text=w, count=c, example=examples.get(w, first_seen[w])) for w, c in counts.items()]
