import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.path_template import (  # noqa: E402
    TemplateValidationError,
    expand_template,
    referenced_tokens,
    validate_template,
)
from arm_common import MediaType  # noqa: E402


def test_expand_template_substitutes_known_tokens() -> None:
    out = expand_template("{title} ({year}).{ext}", {"title": "X", "year": "2010", "ext": "mkv"})
    assert out == "X (2010).mkv"


def test_expand_template_unknown_token_raises() -> None:
    with pytest.raises(TemplateValidationError, match="unknown token"):
        expand_template("{nope}", {})


def test_referenced_tokens() -> None:
    assert referenced_tokens("{a}/{b}-{a}.{c}") == {"a", "b", "c"}


def test_validate_movie_template_happy_path() -> None:
    out = validate_template(
        "{title} ({year})/{title} ({year}) - {transcode_slug}.{ext}",
        MediaType.MOVIE,
        has_transcode_preset=True,
    )
    assert "Iron Man" in out and "plex-1080p-h265" in out and out.endswith(".mkv")


def test_validate_rejects_token_not_allowed_for_media_type() -> None:
    with pytest.raises(TemplateValidationError, match="not allowed for media_type=movie"):
        validate_template("{show}/{ep}.mkv", MediaType.MOVIE, has_transcode_preset=True)


def test_validate_rejects_transcode_slug_without_preset() -> None:
    with pytest.raises(TemplateValidationError, match="transcode preset"):
        validate_template(
            "{title} ({year})/{title} - {transcode_slug}.{ext}",
            MediaType.MOVIE,
            has_transcode_preset=False,
        )


def test_validate_rejects_ext_without_preset_for_non_iso() -> None:
    with pytest.raises(TemplateValidationError, match="ext"):
        validate_template(
            "{title} ({year}).{ext}",
            MediaType.MOVIE,
            has_transcode_preset=False,
        )


def test_validate_iso_template_allows_ext_without_preset() -> None:
    out = validate_template(
        "{title} ({year})/{title} ({year}).{ext}",
        MediaType.ISO,
        has_transcode_preset=False,
    )
    assert out.endswith(".iso")


def test_validate_data_template_minimal() -> None:
    out = validate_template("{title}/", MediaType.DATA, has_transcode_preset=False)
    assert out == "Data Disc/"


def test_validate_tv_template_zero_padded_tokens() -> None:
    out = validate_template(
        "{show} ({year})/Season {season}/{show} - S{season}D{disc}T{track} - {transcode_slug}.{ext}",
        MediaType.TV,
        has_transcode_preset=True,
    )
    assert "S01D01T01" in out


def test_validate_music_template() -> None:
    out = validate_template(
        "{artist}/{album}/{track} - {track_title} - {transcode_slug}.{ext}",
        MediaType.MUSIC,
        has_transcode_preset=True,
    )
    assert "Pink Floyd" in out and "Speak to Me" in out and out.endswith(".flac")


def test_validate_template_or_http_passes_through_expansion() -> None:
    from arm_backend.path_template import validate_template_or_http
    from arm_common.enums import MediaType

    out = validate_template_or_http("{title} ({year})/{title}.mkv", MediaType.MOVIE, True)
    assert "Iron Man" in out


def test_validate_template_or_http_raises_http_422_on_bad_token() -> None:
    import pytest
    from fastapi import HTTPException

    from arm_backend.path_template import validate_template_or_http
    from arm_common.enums import MediaType

    with pytest.raises(HTTPException) as exc:
        validate_template_or_http("{nope}", MediaType.MOVIE, True)
    assert exc.value.status_code == 422


def test_music_allows_disc_token() -> None:
    from arm_backend.path_template import tokens_for_media, validate_template
    from arm_common.enums import MediaType

    keys = {t["token"] for t in tokens_for_media(MediaType.MUSIC)}
    assert "disc" in keys

    # a music template referencing {disc} validates (transcode_slug present -> has preset)
    validate_template(
        "{artist}/{album}/Disc {disc}/{track} - {track_title}.{ext}",
        MediaType.MUSIC,
        has_transcode_preset=True,
    )
