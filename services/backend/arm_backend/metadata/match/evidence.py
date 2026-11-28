"""What a disc says about itself, as evidence a candidate is scored against.

`build_evidence` reads plain inputs (the BDMT name, an ISO file name, the volume label, the scan's titles, the
disc set numbers) and returns a frozen `DiscEvidence`. It reads every title source, not the resolver's one
winner, because scoring weighs each source by how reliable it is. Pure; no I/O.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Literal

from arm_common.disc_shape import (
    EPISODE_MAX_SECONDS,
    EPISODE_MIN_SECONDS,
    FEATURE_MIN_SECONDS,
    MIN_EPISODES,
    SIMILARITY,
    looks_episodic,
)
from arm_common.disc_titles import is_structure_scan, scan_candidates
from arm_common.schemas import ScanResult, ScanTitle
from arm_common.title_classes import KEPT_CLASSES, MAIN_FEATURE_MIN_SECONDS, classify_titles

from arm_backend.metadata.match.tokens import TRUNCATED_LABEL_LENGTH, ParsedTitle, TitleYear, parse_title

TITLE_SOURCES = ("bd_title", "iso_name", "label")

# How far a year read from the text is trusted (spec 1.2).
_PAREN_RELIABILITY = {"iso_name": 0.9, "bd_title": 0.8, "label": 0.3}
_ISO_TRAILING_BARE_RELIABILITY = 0.5
_BARE_RELIABILITY = 0.3

STRUCTURE_RUNTIME_RELIABILITY = 1.0
TITLES_RUNTIME_RELIABILITY = 0.7

P_TV_EPISODIC = 0.90
P_TV_SEASON = 0.80
P_TV_FEATURE = 0.15
P_TV_DISC_MARKER = 0.60
P_TV_NONE = 0.40

# A kept title counts as a version of the feature only from this share of the longest kept title's length.
FEATURE_VERSION_SHARE = 0.7

_ISO_EXTENSION = ".iso"

RuntimeSource = Literal["structure", "titles", "episodes"]


@dataclass(frozen=True)
class TitleEvidence:
    source: str
    text: str
    parsed: ParsedTitle


@dataclass(frozen=True)
class YearEvidence:
    year: int
    sources: tuple[str, ...]
    reliability: float
    # Every source wrote it bare, so a candidate whose title contains the number consumes it.
    bare: bool


@dataclass(frozen=True)
class RuntimeEvidence:
    # Distinct feature runtimes in minutes (several when the disc has editions); empty for an episodic disc.
    feature_minutes: tuple[float, ...]
    # The median episode length of an episodic disc.
    episode_minutes: float | None
    # How far feature_minutes is trusted; unused for an episodic disc.
    reliability: float
    source: RuntimeSource


@dataclass(frozen=True)
class DiscEvidence:
    titles: tuple[TitleEvidence, ...]
    years: tuple[YearEvidence, ...]
    runtime: RuntimeEvidence | None
    # Probability the disc is a TV series, and the signal that decided it.
    p_tv: float
    kind_reasons: tuple[str, ...]
    # (disc number, disc total) of a multi-disc set.
    set_position: tuple[int | None, int | None]
    # An edition word was stripped from a title: the disc may be a cut the providers do not list.
    edition_hint: bool


def _title_evidence(source: str, text: str | None, now_year: int) -> TitleEvidence | None:
    if not text:
        return None
    if source == "iso_name" and text.casefold().endswith(_ISO_EXTENSION):
        text = text[: -len(_ISO_EXTENSION)]
    truncated = source == "label" and len(text) >= TRUNCATED_LABEL_LENGTH
    parsed = parse_title(text, now_year=now_year, truncated=truncated)
    return TitleEvidence(source, text, parsed) if parsed.tokens else None


def _year_reliability(source: str, year: TitleYear) -> float:
    if not year.bare:
        return _PAREN_RELIABILITY[source]
    if source == "iso_name" and year.trailing:
        return _ISO_TRAILING_BARE_RELIABILITY
    return _BARE_RELIABILITY


def _years(titles: Sequence[TitleEvidence]) -> tuple[YearEvidence, ...]:
    """One entry per year; sources that agree combine as 1 - (1 - r1)(1 - r2)."""
    merged: dict[int, YearEvidence] = {}
    for title in titles:
        for year in title.parsed.years:
            r = _year_reliability(title.source, year)
            old = merged.get(year.year)
            if old is None:
                merged[year.year] = YearEvidence(year.year, (title.source,), r, year.bare)
            else:
                merged[year.year] = YearEvidence(
                    year.year, (*old.sources, title.source), 1 - (1 - old.reliability) * (1 - r), old.bare and year.bare
                )
    return tuple(sorted(merged.values(), key=lambda y: (-y.reliability, y.year)))


def _minutes(seconds: float) -> float:
    return round(seconds / 60, 1)


def _episode_seconds(titles: Sequence[ScanTitle]) -> list[int]:
    durations = [t.duration_seconds for t in titles if EPISODE_MIN_SECONDS <= t.duration_seconds <= EPISODE_MAX_SECONDS]
    if len(durations) < MIN_EPISODES:
        return []
    mid = median(durations)
    return [d for d in durations if abs(d - mid) <= SIMILARITY * mid]


def _feature_seconds(titles: Sequence[ScanTitle], structured: bool) -> list[int]:
    if structured:
        verdicts = classify_titles(titles)
        kept = [t for t in titles if verdicts[t.index].title_class in KEPT_CLASSES]
        seconds = [t.duration_seconds for t in kept if t.duration_seconds >= MAIN_FEATURE_MIN_SECONDS]
        # A long extra (a documentary) is kept next to the film but is not a version of it.
        return [d for d in seconds if d >= FEATURE_VERSION_SHARE * max(seconds)]
    longest = max((t.duration_seconds for t in titles), default=0)
    return [longest] if longest >= MAIN_FEATURE_MIN_SECONDS else []


def _runtime(titles: Sequence[ScanTitle], structured: bool) -> RuntimeEvidence | None:
    if looks_episodic(titles):
        episodes = _episode_seconds(titles)
        return RuntimeEvidence((), _minutes(median(episodes)), 0.0, "episodes")
    features = _feature_seconds(titles, structured)
    if not features:
        return None
    minutes = tuple(sorted({_minutes(s) for s in features}))
    if structured:
        return RuntimeEvidence(minutes, None, STRUCTURE_RUNTIME_RELIABILITY, "structure")
    return RuntimeEvidence(minutes, None, TITLES_RUNTIME_RELIABILITY, "titles")


def _set_position(
    titles: Sequence[TitleEvidence], set_number: int | None, num_sets: int | None
) -> tuple[int | None, int | None]:
    if set_number is not None or num_sets is not None:
        return set_number, num_sets
    for title in titles:
        parsed = title.parsed
        if not parsed.part_only and (parsed.disc is not None or parsed.disc_total is not None):
            return parsed.disc, parsed.disc_total
    return None, None


def _disc_marker_reason(position: tuple[int | None, int | None]) -> str | None:
    number, total = position
    if number is not None and total is not None:
        return f"disc {number} of {total}"
    if number is not None:
        return f"disc {number}"
    if total is not None and total > 1:
        return f"{total}-disc set"
    return None


def _kind(
    titles: Sequence[ScanTitle],
    parsed: Sequence[ParsedTitle],
    position: tuple[int | None, int | None],
) -> tuple[float, str]:
    """The first signal that matches decides (spec 1.4); a feature outranks a disc marker."""
    if looks_episodic(titles):
        return P_TV_EPISODIC, f"{len(_episode_seconds(titles))} episode-length titles"
    if any(p.season is not None for p in parsed):
        return P_TV_SEASON, "season marker in label"
    longest = max((t.duration_seconds for t in titles), default=0)
    if longest >= FEATURE_MIN_SECONDS:
        return P_TV_FEATURE, f"single {round(longest / 60)}-min feature"
    reason = _disc_marker_reason(position)
    if reason is not None:
        return P_TV_DISC_MARKER, reason
    return P_TV_NONE, "no kind signal"


def build_evidence(
    *,
    bd_title: str | None,
    iso_name: str | None,
    label: str | None,
    titles: Sequence[ScanTitle],
    structured: bool,
    set_number: int | None,
    num_sets: int | None,
    now: datetime,
) -> DiscEvidence:
    """The evidence of one disc. A title source left None (or disabled by the caller) is skipped.

    `titles`: the scan's candidate titles (`scan_candidates`); `structured`: they come from a Blu-ray structure
    read, so the kept titles of `classify_titles` are the feature versions."""
    texts = {"bd_title": bd_title, "iso_name": iso_name, "label": label}
    found = (_title_evidence(source, texts[source], now.year) for source in TITLE_SOURCES)
    evidence = tuple(t for t in found if t is not None)
    parsed = [t.parsed for t in evidence]
    position = _set_position(evidence, set_number, num_sets)
    p_tv, reason = _kind(titles, parsed, position)
    return DiscEvidence(
        titles=evidence,
        years=_years(evidence),
        runtime=_runtime(titles, structured),
        p_tv=p_tv,
        kind_reasons=(reason,),
        set_position=position,
        edition_hint=any(p.edition for p in parsed),
    )


def evidence_from_scan(
    scan: ScanResult,
    *,
    iso_name: str | None,
    now: datetime,
    enabled: Collection[str] = TITLE_SOURCES,
) -> DiscEvidence:
    """`build_evidence` over a scan: its BDMT name, volume label, candidate titles and set numbers.

    `enabled`: the disc-hint sources the operator keeps on; a disabled source contributes nothing, neither its
    text nor (for the BDMT name) its disc set numbers."""
    meta = scan.bd_meta if "bd_title" in enabled else None
    return build_evidence(
        bd_title=meta.name if meta else None,
        iso_name=iso_name if "iso_name" in enabled else None,
        label=scan.volume_label if "label" in enabled else None,
        titles=scan_candidates(scan),
        structured=is_structure_scan(scan),
        set_number=meta.set_number if meta else None,
        num_sets=meta.num_sets if meta else None,
        now=now,
    )
