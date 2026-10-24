#!/usr/bin/env python3
"""Run the episode matcher over the TheDiscDB TV corpus and report how often
it places titles correctly, under several levels of knowledge about the disc.

    uv run python devtools/tv-match-baseline.py [--min-seconds N] [--series slug ...]

The scenario engine lives in services/backend/tests/tv_match_baseline.py (the
regression test uses it too). Pure: no DB, no network."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "backend"))

from tests.tv_match_baseline import SCENARIOS, Tally, run  # noqa: E402
from tests.thediscdb_corpus import load_corpus  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-seconds", type=int, default=0, help="drop scan titles shorter than this (preset filter)")
    ap.add_argument("--series", nargs="*", help="corpus slugs to run (default: all)")
    args = ap.parse_args()
    corpus = load_corpus()
    slugs = args.series or sorted(corpus)
    header = (
        f"{'':38} {'discs':>5} {'placed':>6} {'correct':>7} {'wrong':>5} {'missed':>6} {'perfect':>7} "
        f"{'suggestion':>10} {'wrongS':>6} {'deep':>5} {'deepWS':>6} {'dups':>4}"
    )
    totals = {name: Tally() for name, *_ in SCENARIOS}
    for slug in slugs:
        series = corpus[slug]
        print(f"\n== {series.title} ({series.year}) [{slug}] discs {len(series.discs)}")
        print(header)
        for name, tally in run(series, args.min_seconds).items():
            print(f"{name:38} {tally.row()}")
            totals[name].add(tally)
    print("\n== all series")
    print(header)
    for name, tally in totals.items():
        acc = tally.correct / tally.placed if tally.placed else 0.0
        print(f"{name:38} {tally.row()}   acc {acc:.0%}")
    print(f"\ncorpus: {len(corpus)} series, {sum(len(s.discs) for s in corpus.values())} discs")


if __name__ == "__main__":
    main()
