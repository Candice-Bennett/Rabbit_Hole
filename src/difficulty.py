from __future__ import annotations

from dataclasses import dataclass

from hsk import HskList
from models import WordCandidate


@dataclass
class LevelStat:
    level: str
    unique: int
    tokens: int


@dataclass
class Difficulty:
    name: str
    levels: list[LevelStat]
    unknown_unique: int
    unknown_tokens: int
    total_unique: int
    total_tokens: int


def analyse(candidates: list[WordCandidate], hsk: HskList) -> Difficulty:
    unique_by_level = {lvl: 0 for lvl in hsk.levels}
    tokens_by_level = {lvl: 0 for lvl in hsk.levels}
    unknown_unique = 0
    unknown_tokens = 0

    for c in candidates:
        level = hsk.level_of(c.text)
        if level is None:
            unknown_unique += 1
            unknown_tokens += c.count
        else:
            unique_by_level[level] += 1
            tokens_by_level[level] += c.count

    levels = [LevelStat(lvl, unique_by_level[lvl], tokens_by_level[lvl]) for lvl in hsk.levels]
    total_unique = sum(l.unique for l in levels) + unknown_unique
    total_tokens = sum(l.tokens for l in levels) + unknown_tokens
    return Difficulty(hsk.name, levels, unknown_unique, unknown_tokens, total_unique, total_tokens)


def pct(part: int, total: int) -> float:
    return part / total * 100 if total else 0.0


def print_difficulty(d: Difficulty) -> None:
    print(f"\n--- {d.name} ---")
    print(f"{'Level':<10}{'unique words':>13}{'%':>7}{'Cumul':>8}{'total count':>13}{'%':>7}{'Cumul':>8}")
    cum_u = cum_t = 0
    for l in d.levels:
        cum_u += l.unique
        cum_t += l.tokens
        print(
            f"{l.level:<10}{l.unique:>13}{pct(l.unique, d.total_unique):>6.1f}%"
            f"{pct(cum_u, d.total_unique):>7.1f}%"
            f"{l.tokens:>13}{pct(l.tokens, d.total_tokens):>6.1f}%"
            f"{pct(cum_t, d.total_tokens):>7.1f}%"
        )
    print(
        f"{'unknown':<10}{d.unknown_unique:>13}{pct(d.unknown_unique, d.total_unique):>6.1f}%{'':>8}"
        f"{d.unknown_tokens:>13}{pct(d.unknown_tokens, d.total_tokens):>6.1f}%"
    )
    print(f"{'total':<10}{d.total_unique:>13}{'':>7}{'':>8}{d.total_tokens:>13}")
