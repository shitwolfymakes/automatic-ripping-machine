"""Music file tags per session: the setting, the tags it keeps, and migrations 0053 and 0054."""

from __future__ import annotations

from arm_backend.music_tag_settings import enabled_music_tags, music_tag_fields_setting, session_music_tags
from arm_common import MediaType, Session
from arm_common.music_tags import MUSIC_TAG_CHOICES
from arm_common.schemas import MusicTags
from tests.test_migration_chain import _render_sql

_FULL = MusicTags(
    artist="Radiohead",
    album_artist="Radiohead",
    album="OK Computer",
    title="Airbag",
    year=1997,
    disc_number=1,
    track_number=1,
    track_total=12,
    musicbrainz_release_id="mb-rel-1",
)
_ALL_TAGS_SQL = (
    "'{artist,album_artist,album,title,track_number,track_total,disc_number,year,musicbrainz_release_id,cover}'::text[]"
)


def _session(**kw: object) -> Session:
    return Session(
        id="ses_music",
        name="Music",
        media_type=MediaType.MUSIC,
        is_builtin=False,
        rip_preset_id="rpr_music",
        output_path_template="{artist}/{album}/{track}",
        **kw,
    )


# --- music_tag_fields_setting ---


def test_a_new_session_writes_every_tag() -> None:
    assert music_tag_fields_setting(_session()) == MUSIC_TAG_CHOICES


def test_setting_is_every_choice_for_a_row_with_no_value() -> None:
    sess = _session()
    sess.music_tag_fields = None  # type: ignore[assignment]
    assert music_tag_fields_setting(sess) == MUSIC_TAG_CHOICES


def test_setting_keeps_known_choices_in_their_own_order() -> None:
    sess = _session(music_tag_fields=["cover", "bogus", "title", "artist"])
    assert music_tag_fields_setting(sess) == ("artist", "title", "cover")


def test_setting_may_switch_every_choice_off() -> None:
    assert music_tag_fields_setting(_session(music_tag_fields=[])) == ()


# --- enabled_music_tags ---


def test_enabled_music_tags_keeps_everything_when_everything_is_on() -> None:
    assert enabled_music_tags(_FULL, MUSIC_TAG_CHOICES) == _FULL


def test_enabled_music_tags_clears_what_is_switched_off() -> None:
    kept = enabled_music_tags(_FULL, ("artist", "title", "track_number", "cover"))
    assert kept == MusicTags(artist="Radiohead", title="Airbag", track_number=1)
    assert _FULL.album == "OK Computer"  # the input is left alone


def test_enabled_music_tags_with_nothing_on_is_empty_not_none() -> None:
    # Still a music track: the transcoder asks for the cover by whether tags came back.
    assert enabled_music_tags(_FULL, ()) == MusicTags()


# --- session_music_tags ---


def test_session_music_tags_is_none_for_a_track_without_tags() -> None:
    assert session_music_tags(None, _session()) is None


def test_session_music_tags_applies_the_session_choice() -> None:
    sess = _session(music_tag_fields=["title", "cover"])
    assert session_music_tags(_FULL, sess) == MusicTags(title="Airbag")


# --- migration 0053: the global setting ---


def test_0053_adds_the_config_column_with_every_tag_on() -> None:
    sql = _render_sql("0052_config_min_title_length", "0053_config_music_tag_fields")
    assert f"ALTER TABLE config ADD COLUMN music_tag_fields VARCHAR[] DEFAULT {_ALL_TAGS_SQL} NOT NULL" in sql


def test_0053_downgrade_drops_the_config_column() -> None:
    sql = _render_sql("0053_config_music_tag_fields", "0052_config_min_title_length", downgrade=True)
    assert "ALTER TABLE config DROP COLUMN music_tag_fields" in sql


# --- migration 0054: the setting moves to sessions ---


def test_0054_moves_the_column_to_sessions_and_keeps_own_music_sessions_choice() -> None:
    sql = _render_sql("0053_config_music_tag_fields", "0054_session_music_tag_fields")
    add = f"ALTER TABLE sessions ADD COLUMN music_tag_fields VARCHAR[] DEFAULT {_ALL_TAGS_SQL} NOT NULL"
    copy = (
        "UPDATE sessions SET music_tag_fields = config.music_tag_fields "
        "FROM config WHERE config.id = 1 AND sessions.media_type = 'music' AND NOT sessions.is_builtin"
    )
    drop = "ALTER TABLE config DROP COLUMN music_tag_fields"
    assert add in sql and copy in sql and drop in sql
    # The copy reads the config column, so it has to run before the drop.
    assert sql.index(add) < sql.index(copy) < sql.index(drop)


def test_0054_default_matches_the_session_model() -> None:
    column = Session.__table__.columns["music_tag_fields"]  # type: ignore[attr-defined]
    assert not column.nullable
    assert column.server_default.arg == "{" + ",".join(MUSIC_TAG_CHOICES) + "}"
    assert _ALL_TAGS_SQL.removesuffix("::text[]") == "'" + column.server_default.arg + "'"


def test_0054_downgrade_puts_the_column_back_on_config() -> None:
    sql = _render_sql("0054_session_music_tag_fields", "0053_config_music_tag_fields", downgrade=True)
    assert f"ALTER TABLE config ADD COLUMN music_tag_fields VARCHAR[] DEFAULT {_ALL_TAGS_SQL} NOT NULL" in sql
    assert "ALTER TABLE sessions DROP COLUMN music_tag_fields" in sql
