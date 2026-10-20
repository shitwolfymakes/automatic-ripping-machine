"""Alembic revision-chain integrity.

Migrations authored on stacked branches can reference a parent revision that
exists on a sibling line but not here (a dangling ``down_revision``). Alembic
only detects that at runtime — the backend's startup ``alembic upgrade head``
crash-loops — so assert the chain is intact statically. No DB required.
"""

import io
import re
from pathlib import Path


from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlmodel import SQLModel

from arm_common import User

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
# `literal_binds`. Everything after it renders (see
# test_every_revision_after_0011_renders_offline); widening to base means
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


def test_every_revision_after_0011_renders_offline() -> None:
    """The data-lift revisions (0032, 0033) iterate SELECT rows from
    ``op.get_bind()``; offline the bind renders statements and returns nothing,
    so ``env.py`` hands back an empty result. Without that, ``--sql`` over any
    range spanning 0032 crashed with ``'NoneType' object is not iterable``."""
    up = _render_sql("0011_plex_movie_track_token", "head")
    assert "-> 0032_job_metadata_sections" in up
    assert "-> 0033_drop_metadata_mirrors" in up
    down = _render_sql("head", "0011_plex_movie_track_token", downgrade=True)
    assert "0033_drop_metadata_mirrors -> 0032_job_metadata_sections" in down


def _migrated_indexes() -> dict[str, tuple[str, tuple[str, ...], bool, str]]:
    """Index inventory at head, read from the rendered DDL. 0011 is skipped (it
    can't render, see above) and creates no indexes."""
    sql = _render_sql("base", "0010_fix_passthrough_mkv_preset") + _render_sql("0011_plex_movie_track_token", "head")
    found: dict[str, tuple[str, tuple[str, ...], bool, str]] = {}
    for stmt in sql.split(";"):
        flat = " ".join(stmt.split())
        created = re.search(r"CREATE (UNIQUE )?INDEX (\w+) ON (\w+) \(([^)]*)\)(?: WHERE (.*))?", flat)
        if created:
            cols = tuple(c.strip() for c in created.group(4).split(","))
            found[created.group(2)] = (created.group(3), cols, bool(created.group(1)), created.group(5) or "")
        dropped = re.search(r"DROP INDEX (\w+)", flat)
        if dropped:
            found.pop(dropped.group(1), None)
    return found


def test_model_indexes_match_migrations() -> None:
    """Metadata-built schemas (the e2e harness, autogenerate) must carry the
    same indexes as the migrated one, including the partial unique index that
    backs the output_path collision check."""
    modelled: dict[str, tuple[str, tuple[str, ...], bool, str]] = {}
    for table in SQLModel.metadata.tables.values():
        for index in table.indexes:
            where = index.dialect_options["postgresql"]["where"]
            modelled[str(index.name)] = (
                table.name,
                tuple(c.name for c in index.columns),
                bool(index.unique),
                str(where) if where is not None else "",
            )
    assert modelled == _migrated_indexes()
