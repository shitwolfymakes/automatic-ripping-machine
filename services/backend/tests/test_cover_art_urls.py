"""`cover_art_urls`: the covers a music track's file may embed, operator override first."""

from typing import Any

from arm_backend.metadata.poster import cover_art_urls
from arm_common import DiscType, Job, JobStatus

_AUTO = "https://coverartarchive.org/release/rel-1/front-250?fallback_group=grp-1"
_AUTO_FULL = "https://coverartarchive.org/release/rel-1/front-500?fallback_group=grp-1"


def _job(**kw: Any) -> Job:
    return Job(id="job_1", drive_id="drv_x", disc_type=DiscType.CD, status=JobStatus.RIPPED, **kw)


def test_override_comes_before_the_automatic_cover() -> None:
    job = _job(poster_url=_AUTO, poster_url_manual="https://posters.lan/mine.jpg")

    assert cover_art_urls(job) == ["https://posters.lan/mine.jpg", _AUTO_FULL]


def test_automatic_cover_art_archive_url_is_upgraded_from_the_thumbnail() -> None:
    assert cover_art_urls(_job(poster_url=_AUTO)) == [_AUTO_FULL]


def test_other_automatic_urls_are_used_as_given() -> None:
    url = "https://image.tmdb.org/t/p/w500/abc-front-250.jpg"

    assert cover_art_urls(_job(poster_url=url)) == [url]


def test_override_is_used_exactly_as_entered() -> None:
    url = "https://coverartarchive.org/release/rel-2/front-250"

    assert cover_art_urls(_job(poster_url_manual=url)) == [url]


def test_override_that_is_not_an_http_url_is_skipped() -> None:
    assert cover_art_urls(_job(poster_url=_AUTO, poster_url_manual="/img/local.jpg")) == [_AUTO_FULL]


def test_override_equal_to_the_automatic_cover_is_tried_once() -> None:
    assert cover_art_urls(_job(poster_url=_AUTO_FULL, poster_url_manual=_AUTO_FULL)) == [_AUTO_FULL]


def test_no_cover_known() -> None:
    assert cover_art_urls(_job()) == []
