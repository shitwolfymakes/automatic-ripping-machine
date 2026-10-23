"""Loader for the TheDiscDB TV corpus under tests/fixtures/thediscdb/ (built
by devtools/thediscdb-fixture.py).

A corpus series plays two roles in a test: the discs are scans (MakeMKV title
order and durations) with the community's episode placement as the oracle,
and the same data seen from the provider side gives an episode list per
season, with runtimes in whole minutes as TMDb reports them. Seasons the
corpus has no disc for are filled from the TMDb season summary with the
show's nominal runtime, or none."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from arm_backend.identity.episodes.model import Episode, TitleIn

CORPUS_DIR = Path(__file__).resolve().parent / "fixtures" / "thediscdb"


@dataclass(frozen=True)
class Title:
    index: int
    source_file: str | None
    duration_s: int
    kind: str | None  # TheDiscDB Item.Type: Episode, Extra, ... or None for untyped
    name: str | None
    season: int | None
    episode: int | None

    @property
    def ref(self) -> str:
        return f"t{self.index}"

    @property
    def is_episode(self) -> bool:
        return self.kind == "Episode" and self.season is not None and self.episode is not None


@dataclass(frozen=True)
class Disc:
    release: str
    index: int | None
    name: str | None
    format: str | None
    content_hash: str | None
    titles: tuple[Title, ...]

    def titles_in(self, min_seconds: int = 0) -> list[TitleIn]:
        """The scan as the episode stage sees it: video titles in MakeMKV
        order with a positive length."""
        return [
            TitleIn(ref=t.ref, seconds=t.duration_s)
            for t in sorted(self.titles, key=lambda t: t.index)
            if t.duration_s > 0 and t.duration_s >= min_seconds
        ]

    @property
    def oracle(self) -> dict[str, tuple[int, int]]:
        """ref -> (season, episode) for every title the community placed."""
        return {t.ref: (t.season, t.episode) for t in self.titles if t.is_episode}  # type: ignore[misc]

    @property
    def seasons(self) -> list[int]:
        return sorted({t.season for t in self.titles if t.is_episode})  # type: ignore[arg-type]

    @property
    def main_season(self) -> int | None:
        """The season most of the placed titles belong to."""
        counts: dict[int, int] = {}
        for t in self.titles:
            if t.is_episode:
                counts[t.season] = counts.get(t.season, 0) + 1  # type: ignore[index]
        return max(counts, key=lambda s: (counts[s], -s)) if counts else None

    @property
    def episode_numbers(self) -> frozenset[int]:
        return frozenset(t.episode for t in self.titles if t.is_episode and t.season == self.main_season)  # type: ignore[misc]


@dataclass(frozen=True)
class Release:
    slug: str
    title: str | None
    discs: tuple[Disc, ...]


@dataclass(frozen=True)
class Series:
    slug: str
    title: str
    year: int | None
    external_ids: dict[str, str | None]
    tmdb_seasons: dict[int, int]  # season number -> episode count
    nominal_runtime_s: int | None
    releases: tuple[Release, ...]

    @property
    def discs(self) -> list[Disc]:
        return [d for r in self.releases for d in r.discs]

    def season_numbers(self) -> list[int]:
        """What `provider.seasons` returns: regular seasons, ascending."""
        on_disc = {t.season for d in self.discs for t in d.titles if t.is_episode}
        return sorted(s for s in set(self.tmdb_seasons) | on_disc if s is not None and s > 0)  # type: ignore[operator]

    @cached_property
    def _by_season(self) -> dict[int, dict[int, Title]]:
        out: dict[int, dict[int, Title]] = {}
        for d in self.discs:
            for t in d.titles:
                if t.is_episode:
                    out.setdefault(t.season, {}).setdefault(t.episode, t)  # type: ignore[arg-type]
        return out

    def episodes(self, season: int) -> list[Episode]:
        """The provider's list for one season: every numbered episode, with
        runtime in whole minutes where a disc knows it, else the show's
        nominal runtime."""
        known = self._by_season.get(season, {})
        count = max(self.tmdb_seasons.get(season, 0), max(known, default=0))
        out = []
        for number in range(1, count + 1):
            t = known.get(number)
            runtime = round(t.duration_s / 60) * 60 if t else self.nominal_runtime_s
            out.append(Episode(season=season, number=number, name=t.name if t else None, runtime_s=runtime))
        return out


def _disc(release: str, raw: dict) -> Disc:
    titles = []
    for t in raw["titles"]:
        item = t["item"]
        titles.append(
            Title(
                index=int(t["index"]),
                source_file=t.get("source_file"),
                duration_s=int(t.get("duration_s") or 0),
                kind=item.get("type"),
                name=item.get("title"),
                season=item.get("season"),
                episode=item.get("episode"),
            )
        )
    return Disc(release, raw.get("index"), raw.get("name"), raw.get("format"), raw.get("content_hash"), tuple(titles))


def load_series(path: Path) -> Series:
    raw = json.loads(path.read_text())
    ert = raw["tmdb"].get("episode_run_time") or []
    return Series(
        slug=path.stem,
        title=raw["title"],
        year=raw.get("year"),
        external_ids=raw["external_ids"],
        tmdb_seasons={int(s["season_number"]): int(s["episode_count"] or 0) for s in raw["tmdb"]["seasons"]},
        nominal_runtime_s=int(ert[0]) * 60 if ert else None,
        releases=tuple(
            Release(r["slug"], r.get("title"), tuple(_disc(r["slug"], d) for d in r["discs"])) for r in raw["releases"]
        ),
    )


def load_corpus(directory: Path = CORPUS_DIR) -> dict[str, Series]:
    return {p.stem: load_series(p) for p in sorted(directory.glob("*.json")) if p.name != "manifest.json"}
