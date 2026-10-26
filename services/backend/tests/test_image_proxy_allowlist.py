"""Tier-3: ARM_EXTRA_IMAGE_HOSTS adds (never replaces) image-proxy allowed hosts."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "x")

from arm_backend.config import Settings  # noqa: E402


def test_extra_hosts_parses_comma_list(monkeypatch):
    monkeypatch.setenv("ARM_EXTRA_IMAGE_HOSTS", "posters.lan, cdn.example.com")
    assert Settings().ARM_EXTRA_IMAGE_HOSTS == ["posters.lan", "cdn.example.com"]  # type: ignore[call-arg]


def test_extra_hosts_default_empty():
    assert Settings().ARM_EXTRA_IMAGE_HOSTS == []  # type: ignore[call-arg]


def test_allowed_hosts_includes_defaults_and_extras(monkeypatch):
    # `settings` is a module singleton evaluated at import, so a post-import
    # setenv wouldn't reach it; _allowed_image_hosts() reads the live object,
    # so patch its attribute directly.
    from arm_backend import config

    monkeypatch.setattr(config.settings, "ARM_EXTRA_IMAGE_HOSTS", ["posters.lan"])
    from arm_backend.routers import images

    hosts = images._allowed_image_hosts()
    assert "image.tmdb.org" in hosts  # built-in default preserved
    assert "posters.lan" in hosts  # extra added


def test_tvmaze_and_tvdb_poster_hosts_are_allowed():
    from arm_backend.routers import images

    assert images._host_allowed("static.tvmaze.com")
    assert images._host_allowed("artworks.thetvdb.com")
    assert not images._host_allowed("static.tvmaze.com.evil.example")
    assert not images._host_allowed("evil-artworks.thetvdb.com")
