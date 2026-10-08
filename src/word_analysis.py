from __future__ import annotations

from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Manager

import hanlp
import torch

from console import fatal
from hanzi import HAS_HANZI, hanzi_count
from models import Sentence, TextAnalysis, WordCandidate
from progress import tqdm

NAME_TAGS = ("nr", "ns")
Segmented = tuple[list[str], set[int]]


class SegmenterError(Exception):
    pass


class Segmenter:
    def __init__(self, force_words: set[str] | None, exclude_names: bool):
        try:
            self.tokenizer = hanlp.load(hanlp.pretrained.tok.COARSE_ELECTRA_SMALL_ZH)
        except Exception as e:
            raise SegmenterError(
                f"Couldn't load the HanLP tokenizer ({e})\n"
                "  - This downloads a model on first run, so make sure you're online\n"
                "  - After a successful run it's cached in ~/.hanlp and no longer needs the internet"
            ) from e
        if force_words:
            self.tokenizer.dict_force = force_words
        self.tagger = None
        if exclude_names:
            try:
                self.tagger = hanlp.load(hanlp.pretrained.pos.PKU_POS_ELECTRA_SMALL)
            except Exception as e:
                raise SegmenterError(
                    f"Couldn't load the HanLP name tagger ({e})\n"
                    "  - This downloads a model on first run, so make sure you're online\n"
                    "  - Or set exclude_names to false in config.json"
                ) from e

    def names_in(self, tokenised: list[list[str]]) -> list[set[int]]:
        if not self.tagger:
            return [set() for _ in tokenised]
        return [
            {i for i, tag in enumerate(tags) if tag.startswith(NAME_TAGS)}
            for tags in self.tagger(tokenised)
        ]

    def __call__(self, texts: list[str]) -> list[Segmented]:
        tokenised = self.tokenizer(texts)
        return list(zip(tokenised, self.names_in(tokenised)))


_worker_segmenter: Segmenter | None = None


def _start_worker(lock, threads: int, force_words: set[str] | None, exclude_names: bool) -> None:
    global _worker_segmenter
    torch.set_num_threads(threads)
    with lock:
        _worker_segmenter = Segmenter(force_words, exclude_names)


def _segment_in_worker(texts: list[str]) -> list[Segmented]:
    return _worker_segmenter(texts)


class WordAnalysisService:
    def __init__(
        self,
        force_words: set[str] | None = None,
        segment_batch_size: int = 32,
        example_sentence_min_hanzi: int = 6,
        example_sentence_max_hanzi: int = 20,
        exclude_names: bool = False,
        segment_workers: int = 1,
    ):
        self.segment_batch_size = segment_batch_size
        self.example_sentence_min_hanzi = example_sentence_min_hanzi
        self.example_sentence_max_hanzi = example_sentence_max_hanzi
        self.segmenter: Segmenter | None = None
        self.pool: ProcessPoolExecutor | None = None
        models = "tokenizer and name tagger" if exclude_names else "tokenizer"
        print(f"Loading HanLP {models} (first run downloads the models, this can take a minute)...")

        if segment_workers <= 1:
            try:
                self.segmenter = Segmenter(force_words, exclude_names)
            except SegmenterError as e:
                fatal(str(e))
            return

        threads = max(1, torch.get_num_threads() // segment_workers)
        self.manager = Manager()
        self.pool = ProcessPoolExecutor(
            segment_workers,
            initializer=_start_worker,
            initargs=(self.manager.Lock(), threads, force_words, exclude_names),
        )
        try:
            list(self.pool.map(_segment_in_worker, [["你好"]] * segment_workers))
        except Exception as e:
            self.close()
            fatal(f"Couldn't start the HanLP workers ({e!r}), see the error above, or set segment_workers to 1")
        print(f"HanLP: segmenting on {segment_workers} workers, {threads} threads each")

    def close(self) -> None:
        if self.pool is not None:
            self.pool.shutdown(cancel_futures=True)
            self.manager.shutdown()
            self.pool = None

    def segment(self, texts: list[str]) -> list[Segmented]:
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        batches = [order[start : start + self.segment_batch_size] for start in range(0, len(order), self.segment_batch_size)]
        texts_by_batch = ([texts[i] for i in batch] for batch in batches)
        if self.pool is not None:
            segmented = self.pool.map(_segment_in_worker, texts_by_batch)
        else:
            segmented = map(self.segmenter, texts_by_batch)

        results: list[Segmented] = [([], set())] * len(texts)
        for batch, batch_results in zip(batches, tqdm(segmented, total=len(batches), desc="segmenting", unit="batch")):
            for i, result in zip(batch, batch_results):
                results[i] = result
        return results

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

        segmented = self.segment([s for _, _, s in sentences])
        for (chapter, paragraph, sentence), (words, names) in zip(sentences, segmented):
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
