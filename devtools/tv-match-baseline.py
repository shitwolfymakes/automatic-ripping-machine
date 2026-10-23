#!/usr/bin/env python3
"""Run the episode matcher over the TheDiscDB TV corpus and report how often
it places titles correctly, under several levels of knowledge about the disc.

    uv run python devtools/tv-match-baseline.py [--min-seconds N] [--series slug ...]

Pure: calls the matcher and continuity code directly, no DB, no network.
Per scenario and series it prints discs, placed titles, correct placements,
wrong placements, oracle episodes the matcher missed, and how many discs would
come back as a suggestion (ambiguous, near tie or sibling conflict)."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "backend"))

from arm_backend.identity.episode_stage import _near_tie  # noqa: E402
from arm_backend.identity.episodes.continuity import SiblingDisc, align_runs, rank_seasons, start_anchor  # noqa: E402
from arm_backend.identity.episodes.model import MatchResult  # noqa: E402
from tests.thediscdb_corpus import Disc, Series, load_corpus  # noqa: E402

TOLERANCE = 300

# (scenario, season known, disc number known, siblings)
SCENARIOS = [
    ("nothing known, scan", False, False, "none"),
    ("season known", True, False, "none"),
    ("season + disc known", True, True, "none"),
    ("season + disc, lower discs held", True, True, "lower"),
    ("season + disc, higher discs held", True, True, "higher"),
    ("season + disc, all others held", True, True, "all"),
    ("season only, lower discs held", True, False, "lower"),
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

    def row(self) -> str:
        return (
            f"{self.discs:>5} {self.placed:>6} {self.correct:>7} {self.wrong:>5} {self.missed:>6} "
            f"{self.perfect:>7} {self.suggestion:>10} {self.wrong_season:>6}"
        )


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
    titles,
    siblings: list[SiblingDisc],
    disc_number: int | None,
    disc_total: int | None,
) -> MatchResult:
    episodes = series.episodes(season)
    remaining, anchor = start_anchor(
        episodes, disc_number=disc_number, disc_total=disc_total, n_titles=len(titles), siblings=siblings
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
            for name, season_known, disc_known, mode in SCENARIOS:
                tally = tallies[name]
                tally.discs += 1
                disc_number = position if disc_known else None
                disc_total = count if disc_known else None
                siblings, conflict = _siblings(disc, discs, mode, season, disc_known) if mode != "none" else ([], False)
                if season_known:
                    picked = season
                    result = _fit(series, disc, season, titles, siblings, disc_number, disc_total)
                    near_tie = False
                else:
                    seasons = series.season_numbers()
                    fits = {s: _fit(series, disc, s, titles, siblings, disc_number, disc_total) for s in seasons}
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
    return tallies


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-seconds", type=int, default=0, help="drop scan titles shorter than this (preset filter)")
    ap.add_argument("--series", nargs="*", help="corpus slugs to run (default: all)")
    args = ap.parse_args()
    corpus = load_corpus()
    slugs = args.series or sorted(corpus)
    header = f"{'':38} {'discs':>5} {'placed':>6} {'correct':>7} {'wrong':>5} {'missed':>6} {'perfect':>7} {'suggestion':>10} {'wrongS':>6}"
    totals: dict[str, Tally] = {name: Tally() for name, *_ in SCENARIOS}
    for slug in slugs:
        series = corpus[slug]
        print(f"\n== {series.title} ({series.year}) [{slug}] discs {len(series.discs)}")
        print(header)
        for name, tally in run(series, args.min_seconds).items():
            print(f"{name:38} {tally.row()}")
            t = totals[name]
            for k, v in vars(tally).items():
                setattr(t, k, getattr(t, k) + v)
    print("\n== all series")
    print(header)
    for name, tally in totals.items():
        acc = tally.correct / tally.placed if tally.placed else 0.0
        print(f"{name:38} {tally.row()}   acc {acc:.0%}")
    c = Counter()
    for s in corpus.values():
        c["discs"] += len(s.discs)
    print(f"\ncorpus: {len(corpus)} series, {c['discs']} discs")


if __name__ == "__main__":
    main()
