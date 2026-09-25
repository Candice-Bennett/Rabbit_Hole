from __future__ import annotations

import re
from collections import Counter

import hanlp

from console import fatal
from models import Sentence, TextAnalysis, WordCandidate
from progress import tqdm

HAS_HANZI = re.compile(r"[一-鿿]")
NAME_TAGS = ("nr", "ns")


def hanzi_count(text: str) -> int:
    return len(HAS_HANZI.findall(text))


class WordAnalysisService:
    def __init__(
        self,
        force_words: set[str] | None = None,
        segment_batch_size: int = 32,
        example_sentence_min_hanzi: int = 6,
        example_sentence_max_hanzi: int = 20,
        exclude_names: bool = False,
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
        self.tagger = None
        if exclude_names:
            print("Loading HanLP name tagger (first run downloads the model, this can take a minute)...")
            try:
                self.tagger = hanlp.load(hanlp.pretrained.pos.PKU_POS_ELECTRA_SMALL)
            except Exception as e:
                fatal(
                    f"Couldn't load the HanLP name tagger ({e})\n"
                    "  - This downloads a model on first run, so make sure you're online\n"
                    "  - Or set exclude_names to false in config.json"
                )

    def names_in(self, tokenised: list[list[str]]) -> list[set[int]]:
        if not self.tagger:
            return [set() for _ in tokenised]
        return [
            {i for i, tag in enumerate(tags) if tag.startswith(NAME_TAGS)}
            for tags in self.tagger(tokenised)
        ]

    def analyse(self, chapters: list[str]) -> TextAnalysis:
        paragraphs = [(i, p) for i, chapter in enumerate(chapters) for p in chapter.split("\n") if p.strip()]
        sentences = [
            (chapter, paragraph, s.strip())
            for paragraph, (chapter, text) in enumerate(paragraphs)
            for s in hanlp.utils.rules.split_sentence(text)
            if s.strip()
        ]

        counts: Counter = Counter()
        examples: dict[str, str] = {}
        first_seen: dict[str, str] = {}
        words_by_chapter: list[list[str]] = [[] for _ in chapters]
        kept_sentences: list[Sentence] = []

        batches = range(0, len(sentences), self.segment_batch_size)
        for start in tqdm(batches, desc="segmenting", unit="batch"):
            batch = sentences[start : start + self.segment_batch_size]
            tokenised = self.tokenizer([s for _, _, s in batch])
            for (chapter, paragraph, sentence), words, names in zip(batch, tokenised, self.names_in(tokenised)):
                usable = self.example_sentence_min_hanzi <= hanzi_count(sentence) <= self.example_sentence_max_hanzi
                kept = []
                for i, word in enumerate(words):
                    if not HAS_HANZI.search(word):
                        continue
                    if i in names:
                        continue
                    kept.append(word)
                    counts[word] += 1
                    words_by_chapter[chapter].append(word)
                    if word not in first_seen:
                        first_seen[word] = sentence
                    if usable and word not in examples:
                        examples[word] = sentence
                kept_sentences.append(Sentence(sentence, kept, chapter, paragraph))

        candidates = [WordCandidate(text=w, count=c, example=examples.get(w, first_seen[w])) for w, c in counts.items()]
        return TextAnalysis(candidates, words_by_chapter, kept_sentences)
