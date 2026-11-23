"""The cover art size a music session embeds: the model default and migration 0055."""

from arm_common import MediaType, Session
from arm_common.enums import MusicCoverSize
from tests.test_migration_chain import _render_sql

_PARENT = "0054_session_music_tag_fields"
_REV = "0055_session_music_cover_size"


def test_a_new_session_embeds_the_500px_cover() -> None:
    sess = Session(name="Music", media_type=MediaType.MUSIC, rip_preset_id="rpr", output_path_template="{album}")
    assert sess.music_cover_size == MusicCoverSize.PX_500


def test_the_column_default_matches_the_model() -> None:
    column = Session.__table__.columns["music_cover_size"]  # type: ignore[attr-defined]
    assert not column.nullable
    assert column.server_default.arg == MusicCoverSize.PX_500.value


def test_0055_adds_the_column_at_500px_for_every_session() -> None:
    sql = _render_sql(_PARENT, _REV)
    assert "ALTER TABLE sessions ADD COLUMN music_cover_size VARCHAR DEFAULT '500' NOT NULL" in sql


def test_0055_downgrade_drops_the_column() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    assert "ALTER TABLE sessions DROP COLUMN music_cover_size" in sql
