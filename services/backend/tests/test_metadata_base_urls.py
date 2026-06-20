"""Tier-3: metadata base URLs are env-overridable, defaulting to current literals."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "x")

from arm_backend.config import Settings  # noqa: E402


def test_base_url_defaults_match_current_literals():
    s = Settings()  # type: ignore[call-arg]
    assert s.ARM_TMDB_BASE_URL == "https://api.themoviedb.org/3"
    assert s.ARM_OMDB_BASE_URL == "https://www.omdbapi.com/"
    assert s.ARM_TVDB_BASE_URL == "https://api4.thetvdb.com/v4"
    assert s.ARM_MUSICBRAINZ_BASE_URL == "https://musicbrainz.org/ws/2"
    assert s.ARM_ARMSERVER_BASE_URL == "https://1337server.pythonanywhere.com/api/v1/"


def test_base_url_overridable_via_env(monkeypatch):
    monkeypatch.setenv("ARM_TMDB_BASE_URL", "http://tmdb-mirror.lan/3")
    assert Settings().ARM_TMDB_BASE_URL == "http://tmdb-mirror.lan/3"  # type: ignore[call-arg]
