"""`cover_art_candidates`: the covers a music track's file may embed, operator
override first, each as its URLs to try, largest first."""

from typing import Any

import pytest

from arm_backend.metadata.poster import cover_art_candidates
from arm_common.enums import MusicCoverSize
from arm_common import DiscType, Job, JobStatus

_AUTO = "https://coverartarchive.org/release/rel-1/front-250?fallback_group=grp-1"


def _caa(path: str) -> str:
    return f"https://coverartarchive.org/release/rel-1/{path}?fallback_group=grp-1"


def _job(**kw: Any) -> Job:
    return Job(id="job_1", drive_id="drv_x", disc_type=DiscType.CD, status=JobStatus.RIPPED, **kw)


def test_override_comes_before_the_automatic_cover() -> None:
    job = _job(poster_url=_AUTO, poster_url_manual="https://posters.lan/mine.jpg")

    assert cover_art_candidates(job, MusicCoverSize.PX_500) == [
        ("https://posters.lan/mine.jpg",),
        (_caa("front-500"), _caa("front-250")),
    ]


@pytest.mark.parametrize(
    ("size", "paths"),
    [
        (MusicCoverSize.SOURCE, ["front", "front-1200", "front-500", "front-250"]),
        (MusicCoverSize.PX_1200, ["front-1200", "front-500", "front-250"]),
        (MusicCoverSize.PX_500, ["front-500", "front-250"]),
        (MusicCoverSize.PX_250, ["front-250"]),
    ],
)
def test_automatic_cover_comes_in_the_session_size_then_each_smaller(size: MusicCoverSize, paths: list[str]) -> None:
    assert cover_art_candidates(_job(poster_url=_AUTO), size) == [tuple(_caa(p) for p in paths)]


def test_a_size_read_back_as_a_plain_string_steps_down_too() -> None:
    assert cover_art_candidates(_job(poster_url=_AUTO), "1200") == [  # type: ignore[arg-type]
        (_caa("front-1200"), _caa("front-500"), _caa("front-250"))
    ]


def test_a_cover_art_archive_url_with_no_thumbnail_is_tried_once() -> None:
    url = "https://coverartarchive.org/release/rel-1/front-500"

    assert cover_art_candidates(_job(poster_url=url), MusicCoverSize.SOURCE) == [(url,)]


def test_other_automatic_urls_are_used_as_given() -> None:
    url = "https://image.tmdb.org/t/p/w500/abc-front-250.jpg"

    assert cover_art_candidates(_job(poster_url=url), MusicCoverSize.SOURCE) == [(url,)]


@pytest.mark.parametrize("size", list(MusicCoverSize))
def test_override_is_used_exactly_as_entered_whatever_the_size(size: MusicCoverSize) -> None:
    url = "https://coverartarchive.org/release/rel-2/front-250"

    assert cover_art_candidates(_job(poster_url_manual=url), size) == [(url,)]


def test_override_that_is_not_an_http_url_is_skipped() -> None:
    job = _job(poster_url=_AUTO, poster_url_manual="/img/local.jpg")

    assert cover_art_candidates(job, MusicCoverSize.PX_500) == [(_caa("front-500"), _caa("front-250"))]


def test_override_equal_to_the_automatic_cover_is_tried_once_with_its_smaller_sizes() -> None:
    job = _job(poster_url=_AUTO, poster_url_manual=_caa("front-1200"))

    assert cover_art_candidates(job, MusicCoverSize.PX_1200) == [
        (_caa("front-1200"), _caa("front-500"), _caa("front-250"))
    ]


def test_override_equal_to_a_smaller_automatic_size_still_comes_first() -> None:
    job = _job(poster_url=_AUTO, poster_url_manual=_caa("front-250"))

    assert cover_art_candidates(job, MusicCoverSize.PX_500) == [
        (_caa("front-250"),),
        (_caa("front-500"), _caa("front-250")),
    ]


def test_no_cover_known() -> None:
    assert cover_art_candidates(_job(), MusicCoverSize.PX_500) == []
