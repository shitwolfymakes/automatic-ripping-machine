"""The TheDiscDB TV corpus loads and exposes what matcher tests need."""

from __future__ import annotations

import json

from tests.thediscdb_corpus import CORPUS_DIR, load_corpus


def test_corpus_matches_its_manifest() -> None:
    manifest = json.loads((CORPUS_DIR / "manifest.json").read_text())
    corpus = load_corpus()
    assert set(corpus) == set(manifest["series"])
    assert manifest["commit"]
    for slug, info in manifest["series"].items():
        series = corpus[slug]
        assert len(series.releases) == info["releases"]
        assert len(series.discs) == info["discs"]
        assert sum(1 for d in series.discs for t in d.titles if t.is_episode) == info["episodes"]


def test_disc_view_is_in_makemkv_order_and_oracle_is_placed_titles() -> None:
    futurama = load_corpus()["futurama"]
    disc = futurama.discs[0]
    titles = disc.titles_in(60)
    assert [t.ref for t in titles] == sorted((t.ref for t in titles), key=lambda r: int(r[1:]))
    assert all(t.seconds >= 60 for t in titles)
    assert disc.main_season == 6
    assert disc.oracle["t1"] == (6, 18)  # playlists are shuffled against episode order
    assert disc.oracle["t7"] == (6, 14)
    assert "t0" not in disc.oracle  # a menu stub is not an episode


def test_provider_view_fills_the_season_from_tmdb_with_minute_runtimes() -> None:
    futurama = load_corpus()["futurama"]
    assert futurama.external_ids["tmdb"] == "615"
    assert futurama.season_numbers()[:3] == [1, 2, 3]
    episodes = futurama.episodes(6)
    assert [e.number for e in episodes] == list(range(1, len(episodes) + 1))
    by_number = {e.number: e for e in episodes}
    assert by_number[18].name == "The Silence of the Clamps"
    assert by_number[18].runtime_s == 1320  # 1300 s on disc, reported in whole minutes
    assert by_number[1].runtime_s is None  # no disc in the corpus, no nominal runtime for this show
