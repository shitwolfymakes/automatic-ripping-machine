"""Episode-matching value types. Pure data; no provider specifics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Episode:
    season: int
    number: int
    name: str | None = None
    runtime_s: int | None = None
    # Absolute numbering / specials: carried for sources that have them (TVDB,
    # AniDB); the matcher only uses order and runtime.
    absolute: int | None = None
    special: bool = False


@dataclass(frozen=True)
class TitleIn:
    ref: str
    seconds: int


@dataclass(frozen=True)
class TitleMatch:
    ref: str
    season: int
    episode: int
    episode_end: int | None
    name: str | None
    delta_s: int | None
    confidence: float


@dataclass(frozen=True)
class MatchResult:
    matches: tuple[TitleMatch, ...]
    skipped: tuple[str, ...]
    play_all: tuple[str, ...]
    cost: float
    coverage: float
    # True when shifting every single-episode match one list position either
    # way is also valid and fits about as well (within AMBIGUITY_WINDOW_S):
    # the positions were decided by the anchor / list order, not by runtimes.
    ambiguous: bool = False
