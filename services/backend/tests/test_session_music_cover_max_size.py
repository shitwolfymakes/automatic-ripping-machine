"""The largest cover file a music session embeds: the model default and migration 0056."""

from arm_common import MediaType, Session
from arm_common.enums import MusicCoverMaxSize
from tests.test_migration_chain import _render_sql

_PARENT = "0055_session_music_cover_size"
_REV = "0056_session_cover_max_size"


def test_a_new_session_limits_the_cover_to_2mb() -> None:
    sess = Session(name="Music", media_type=MediaType.MUSIC, rip_preset_id="rpr", output_path_template="{album}")
    assert sess.music_cover_max_size == MusicCoverMaxSize.MB_2


def test_the_column_default_matches_the_model() -> None:
    column = Session.__table__.columns["music_cover_max_size"]  # type: ignore[attr-defined]
    assert not column.nullable
    assert column.server_default.arg == MusicCoverMaxSize.MB_2.value


def test_0056_adds_the_column_at_2mb_for_every_session() -> None:
    sql = _render_sql(_PARENT, _REV)
    assert "ALTER TABLE sessions ADD COLUMN music_cover_max_size VARCHAR DEFAULT '2mb' NOT NULL" in sql


def test_0056_downgrade_drops_the_column() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    assert "ALTER TABLE sessions DROP COLUMN music_cover_max_size" in sql
