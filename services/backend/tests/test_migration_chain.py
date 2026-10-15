"""Alembic revision-chain integrity.

Migrations authored on stacked branches can reference a parent revision that
exists on a sibling line but not here (a dangling ``down_revision``). Alembic
only detects that at runtime — the backend's startup ``alembic upgrade head``
crash-loops — so assert the chain is intact statically. No DB required.
"""

import io
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402

from arm_common import User  # noqa: E402

_BACKEND_DIR = Path(__file__).parent.parent


def _script_directory() -> ScriptDirectory:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "migrations"))
    return ScriptDirectory.from_config(cfg)


def test_every_down_revision_resolves() -> None:
    """Walking base→heads forces the full revision map; a dangling
    down_revision (or duplicate id) raises here instead of at backend boot."""
    script = _script_directory()
    revisions = list(script.walk_revisions("base", "heads"))
    assert revisions, "no migrations found"


def test_single_linear_head() -> None:
    """Two heads mean two migrations claim the same parent — ``alembic
    upgrade head`` refuses to run until a merge revision reconciles them."""
    script = _script_directory()
    heads = script.get_heads()
    assert len(heads) == 1, f"expected one migration head, found {heads}"


def _render_sql(from_rev: str, to_rev: str, *, downgrade: bool = False) -> str:
    """Run a migration range in Alembic's offline mode and return the DDL.

    Offline mode executes each revision's ``upgrade()``/``downgrade()`` body
    for real but renders SQL instead of connecting, so this stays zero-infra
    while still catching a typo'd column or a bad table reference that a
    static read of the file would miss.
    """
    buf = io.StringIO()
    # Built WITHOUT the ini path on purpose. `migrations/env.py` calls
    # `fileConfig(config.config_file_name)` whenever one is set, and that
    # reconfigures logging process-wide with disable_existing_loggers=True —
    # silencing every logger already created and breaking unrelated caplog
    # assertions across the suite. Leaving config_file_name None skips it; the
    # ini's only non-logging settings are re-declared here.
    cfg = Config(output_buffer=buf)
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "migrations"))
    cfg.set_main_option("prepend_sys_path", str(_BACKEND_DIR))
    cfg.set_main_option("version_path_separator", "os")
    revision_range = f"{from_rev}:{to_rev}"
    if downgrade:
        command.downgrade(cfg, revision_range, sql=True)
    else:
        command.upgrade(cfg, revision_range, sql=True)
    return buf.getvalue()


# The full base:head range can't be rendered offline: 0011_plex_movie_track_token
# seeds rows through a parameterised statement that raises CompileError under
# `literal_binds`. Scoped to the range this branch introduced; widening it means
# rewriting that seed first.
_PARENT_REV = "0026_add_makemkv_sdf_columns"
_REV = "0028_user_role_disabled"


def test_0028_upgrade_adds_the_user_role_columns() -> None:
    sql = _render_sql(_PARENT_REV, _REV)
    assert "ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'admin' NOT NULL" in sql
    assert "ALTER TABLE users ADD COLUMN disabled BOOLEAN DEFAULT 'false' NOT NULL" in sql


def test_0028_downgrade_drops_the_user_role_columns() -> None:
    sql = _render_sql(_REV, _PARENT_REV, downgrade=True)
    assert "ALTER TABLE users DROP COLUMN disabled" in sql
    assert "ALTER TABLE users DROP COLUMN role" in sql


def test_0028_matches_the_user_model() -> None:
    """Model↔migration parity for the columns this branch adds. A field renamed
    or made nullable on `User` without touching 0028 leaves the app querying a
    column the schema doesn't have — a boot-time failure, not a test failure,
    without this."""
    sql = _render_sql(_PARENT_REV, _REV)
    for name in ("role", "disabled"):
        column = User.__table__.columns[name]
        assert f"ADD COLUMN {name} " in sql, f"0028 does not add users.{name}"
        assert not column.nullable, f"User.{name} is nullable but 0028 declares NOT NULL"
        assert column.server_default is not None, f"User.{name} has no server_default to match 0028's"


_IDENT_PARENT = "0044_previously_ripped"
_IDENT_REV = "0045_identification_sources"


def test_0045_upgrade_adds_the_identification_columns_and_seeds_them() -> None:
    sql = _render_sql(_IDENT_PARENT, _IDENT_REV)
    assert "ALTER TABLE config ADD COLUMN movie_sources VARCHAR[] DEFAULT '{tmdb,omdb}'::text[] NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN music_sources VARCHAR[] DEFAULT '{musicbrainz}'::text[] NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN search_provider_movie VARCHAR DEFAULT 'tmdb' NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN search_provider_tv VARCHAR DEFAULT 'tmdb' NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN search_provider_music VARCHAR DEFAULT 'musicbrainz' NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN movie_auto_apply BOOLEAN DEFAULT true NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN music_auto_apply BOOLEAN DEFAULT true NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN crc64service_enabled BOOLEAN DEFAULT true NOT NULL" in sql
    # D-8: the old choice goes first in the movie order and stays the search provider.
    assert "WHEN metadata_provider = 'omdb' THEN '{omdb,tmdb}'::text[]" in sql
    assert "WHEN metadata_provider IN ('tmdb', 'omdb') THEN metadata_provider" in sql
    assert "COALESCE(episode_sources[1], 'tmdb')" in sql
    assert sql.index("UPDATE config SET") < sql.index("ALTER TABLE config DROP COLUMN metadata_provider")


def test_0045_downgrade_restores_metadata_provider_from_the_movie_order() -> None:
    sql = _render_sql(_IDENT_REV, _IDENT_PARENT, downgrade=True)
    assert "ALTER TABLE config ADD COLUMN metadata_provider VARCHAR DEFAULT 'tmdb' NOT NULL" in sql
    assert "WHEN movie_sources[1] IN ('tmdb', 'omdb') THEN movie_sources[1]" in sql
    for name in (
        "crc64service_enabled",
        "music_auto_apply",
        "movie_auto_apply",
        "search_provider_music",
        "search_provider_tv",
        "search_provider_movie",
        "music_sources",
        "movie_sources",
    ):
        assert f"ALTER TABLE config DROP COLUMN {name}" in sql


def test_0045_matches_the_config_model() -> None:
    from arm_common import Config as ConfigModel

    sql = _render_sql(_IDENT_PARENT, _IDENT_REV)
    for name in (
        "movie_sources",
        "music_sources",
        "search_provider_movie",
        "search_provider_tv",
        "search_provider_music",
        "movie_auto_apply",
        "music_auto_apply",
        "crc64service_enabled",
    ):
        column = ConfigModel.__table__.columns[name]
        assert f"ADD COLUMN {name} " in sql, f"0045 does not add config.{name}"
        assert not column.nullable, f"Config.{name} is nullable but 0045 declares NOT NULL"
        assert column.server_default is not None, f"Config.{name} has no server_default to match 0045's"
    assert "metadata_provider" not in ConfigModel.__table__.columns
