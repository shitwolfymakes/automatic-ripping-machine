"""The scenario engine behind devtools/tv-match-baseline.py and the baseline
regression test: runs the episode matcher over the TheDiscDB TV corpus under
several levels of knowledge about the disc.

Pure: calls the matcher and continuity code directly, no DB, no network.
Per scenario and series it tallies discs, placed titles, correct placements,
wrong placements, oracle episodes the matcher missed, and how many discs would
come back as a suggestion (ambiguous, near tie or sibling conflict)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields

from arm_backend.identity.episode_stage import (
    _near_tie,
    _SeasonFit,
    episode_shaped_count,
    hold_reasons,
    season_scan_order,
)
from arm_backend.identity.episodes.continuity import SiblingDisc, align_runs, rank_seasons, start_anchor
from arm_backend.identity.episodes.model import MatchResult, TitleIn
from tests.thediscdb_corpus import Disc, Series

TOLERANCE = 300
DEEP_SEASON = 11  # discs whose true season is this or later count as deep

# (scenario, season known, disc number known, siblings, variant); variant "hint"
# scans from the season the disc's name carries, "hand" places one track by hand.
SCENARIOS = [
    ("nothing known, scan", False, False, "none", ""),
    ("nothing known, hint-ordered scan", False, False, "none", "hint"),
    ("season known", True, False, "none", ""),
    ("season known, one track placed by hand", True, False, "none", "hand"),
    ("season + disc known", True, True, "none", ""),
    ("season + disc, lower discs held", True, True, "lower", ""),
    ("season + disc, higher discs held", True, True, "higher", ""),
    ("season + disc, all others held", True, True, "all", ""),
    ("season only, lower discs held", True, False, "lower", ""),
]


@dataclass
class Tally:
    discs: int = 0
    placed: int = 0
    correct: int = 0
    wrong: int = 0
    missed: int = 0
    perfect: int = 0
    suggestion: int = 0
    wrong_season: int = 0
    deep_discs: int = 0
    deep_wrong_season: int = 0
    duplicates: int = 0

    def row(self) -> str:
        return (
            f"{self.discs:>5} {self.placed:>6} {self.correct:>7} {self.wrong:>5} {self.missed:>6} "
            f"{self.perfect:>7} {self.suggestion:>10} {self.wrong_season:>6} "
            f"{self.deep_discs:>5} {self.deep_wrong_season:>6} {self.duplicates:>4}"
        )

    def add(self, other: Tally) -> None:
        for f in fields(self):
            setattr(self, f.name, getattr(self, f.name) + getattr(other, f.name))


def _siblings(
    disc: Disc, others: Sequence[Disc], mode: str, season: int, disc_known: bool
) -> tuple[list[SiblingDisc], bool]:
    """Mimic `episode_stage._siblings`: only a sibling with a known, different
    disc number claims its episodes; any other sibling holding episodes of
    this season is a conflict."""
    out: list[SiblingDisc] = []
    conflict = False
    mine, _ = _season_position(disc, others)
    for o in others:
        if o is disc or season not in o.seasons:
            continue
        held = frozenset(t.episode for t in o.titles if t.is_episode and t.season == season)  # type: ignore[misc]
        if not held:
            continue
        theirs = _season_position(o, others)[0] if o.main_season == season else None
        if mode == "lower" and not (theirs is not None and theirs < mine):
            continue
        if mode == "higher" and not (theirs is not None and theirs > mine):
            continue
        if disc_known and theirs is not None and theirs != mine:
            out.append(SiblingDisc(theirs, held))
        else:
            conflict = True
    return out, conflict


def _fit(
    series: Series,
    disc: Disc,
    season: int,
    titles: Sequence[TitleIn],
    siblings: list[SiblingDisc],
    disc_number: int | None,
    disc_total: int | None,
) -> MatchResult:
    episodes = series.episodes(season)
    remaining, anchor = start_anchor(
        episodes,
        disc_number=disc_number,
        disc_total=disc_total,
        n_titles=episode_shaped_count(titles, episodes, TOLERANCE),
        siblings=siblings,
    )
    claimed = frozenset().union(*(s.episodes for s in siblings)) if siblings else frozenset()
    return align_runs(titles, remaining, claimed=claimed, tolerance=TOLERANCE, anchor=anchor)


def _season_position(disc: Disc, discs: Sequence[Disc]) -> tuple[int, int]:
    """What a `S<n> D<m>` label says: this disc's rank among the release's
    discs of the same season, and how many there are. A complete-series
    release numbers its discs across seasons, which no label does."""
    same = [d for d in discs if d.main_season == disc.main_season]
    same.sort(key=lambda d: (d.index is None, d.index))
    return same.index(disc) + 1, len(same)


def _hinted_scan(
    series: Series, disc: Disc, titles: Sequence[TitleIn], siblings: list[SiblingDisc], conflict: bool
) -> tuple[int, MatchResult, bool]:
    """The backend's hint-ordered scan: the season in the disc's name first,
    stopping as soon as a hinted season ranks first and nothing holds it."""
    found = re.search(r"Season (\d+)", disc.name or "")
    order = season_scan_order(series.season_numbers(), hint=int(found.group(1)) if found else None, sibling_seasons=[])
    fits: dict[int, _SeasonFit] = {}
    ranked: list[tuple[int, MatchResult]] = []
    for s, from_hint in order:
        fits[s] = _SeasonFit(_fit(series, disc, s, titles, siblings, None, None), False, conflict)
        ranked = rank_seasons({k: f.result for k, f in fits.items()})
        if from_hint and ranked[0][0] == s and not hold_reasons(fits[s], ranked, scanned=True, auto_apply=True):
            break
    picked, result = ranked[0]
    return picked, result, len(ranked) > 1 and _near_tie(result, ranked[1][1])


def run(series: Series, min_seconds: int) -> dict[str, Tally]:
    tallies = {name: Tally() for name, *_ in SCENARIOS}
    for release in series.releases:
        discs = list(release.discs)
        for disc in discs:
            season = disc.main_season
            titles = disc.titles_in(min_seconds)
            if season is None or not titles:
                continue
            oracle = disc.oracle
            # An Episode-kind title TheDiscDB left unnumbered (a feature-length
            # opener split later by the provider) is neither right nor wrong.
            unnumbered = {t.ref for t in disc.titles if t.kind == "Episode" and not t.is_episode}
            position, count = _season_position(disc, discs)
            for name, season_known, disc_known, mode, variant in SCENARIOS:
                tally = tallies[name]
                tally.discs += 1
                deep = season >= DEEP_SEASON
                tally.deep_discs += deep
                disc_number = position if disc_known else None
                disc_total = count if disc_known else None
                siblings, conflict = _siblings(disc, discs, mode, season, disc_known) if mode != "none" else ([], False)
                scan_titles = titles
                hand_episode: int | None = None
                if variant == "hand":
                    hand = next(
                        (
                            t
                            for t in sorted(disc.titles, key=lambda t: t.index)
                            if t.is_episode and t.season == season and t.ref in {x.ref for x in titles}
                        ),
                        None,
                    )
                    if hand is not None:
                        hand_episode = hand.episode
                        scan_titles = [t for t in titles if t.ref != hand.ref]
                        siblings = [*siblings, SiblingDisc(None, frozenset({hand.episode}))]  # type: ignore[arg-type]
                if season_known:
                    picked = season
                    result = _fit(series, disc, season, scan_titles, siblings, disc_number, disc_total)
                    near_tie = False
                elif variant == "hint":
                    picked, result, near_tie = _hinted_scan(series, disc, scan_titles, siblings, conflict)
                else:
                    seasons = series.season_numbers()
                    fits = {s: _fit(series, disc, s, scan_titles, siblings, disc_number, disc_total) for s in seasons}
                    ranked = rank_seasons(fits)
                    picked, result = ranked[0]
                    near_tie = len(ranked) > 1 and _near_tie(result, ranked[1][1])
                placed = {m.ref: (picked, m.episode) for m in result.matches if m.ref not in unnumbered}
                tally.placed += len(placed)
                ok = sum(1 for ref, se in placed.items() if oracle.get(ref) == se)
                tally.correct += ok
                tally.wrong += len(placed) - ok
                tally.missed += sum(1 for ref in oracle if ref not in placed)
                if ok == len(placed) == len(oracle):
                    tally.perfect += 1
                if result.ambiguous or near_tie or conflict:
                    tally.suggestion += 1
                if picked != season:
                    tally.wrong_season += 1
                    tally.deep_wrong_season += deep
                if hand_episode is not None:
                    tally.duplicates += sum(1 for m in result.matches if m.episode == hand_episode)
    return tallies


def run_all(corpus: Mapping[str, Series], min_seconds: int) -> dict[str, Tally]:
    """Every scenario's tally summed over the given series."""
    totals = {name: Tally() for name, *_ in SCENARIOS}
    for series in corpus.values():
        for name, tally in run(series, min_seconds).items():
            totals[name].add(tally)
    return totals
