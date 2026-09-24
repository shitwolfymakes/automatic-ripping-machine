"""Direct seeders coverage: admin idempotency + first-boot banner write,
config signing-key back-fill, and _insert_missing idempotency.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from arm_backend import seeders  # noqa: E402
from arm_backend.seeders import (  # noqa: E402
    _seed_admin_user,
    _seed_config_singleton,
    _seed_session_routes,
    run_seeders,
)
from arm_common import Config, DiscType, MediaType, RetentionPolicy, SessionRoute, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


async def test_seed_admin_writes_banner_then_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seeders, "FIRST_BOOT_LOG", tmp_path / "logs" / "first-boot.log")
    db = FakeSession()
    await _seed_admin_user(db)
    created = [u for u in db.added if isinstance(u, User)]
    assert len(created) == 1
    assert (tmp_path / "logs" / "first-boot.log").read_text().count("default admin credentials") == 1

    # Second run: admin already present → early return, no second insert.
    await _seed_admin_user(db)
    assert len([u for u in db.added if isinstance(u, User)]) == 1


async def test_seed_admin_swallows_banner_write_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    # Point FIRST_BOOT_LOG at a path whose parent can't be created (a file
    # standing in for the parent dir) → mkdir/open raise OSError, swallowed.
    bad_parent = Path("/proc/cpuinfo/sub/first-boot.log")
    monkeypatch.setattr(seeders, "FIRST_BOOT_LOG", bad_parent)
    db = FakeSession()
    await _seed_admin_user(db)  # must not raise
    assert len([u for u in db.added if isinstance(u, User)]) == 1


async def test_seed_config_backfills_missing_signing_key() -> None:
    db = FakeSession()
    db.rows["config"] = [
        Config(
            id=1,
            auto_transcode_on_idle=False,
            auto_rip_on_insert=True,
            block_on_miss=True,
            default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
            session_signing_key=None,
        )
    ]
    await _seed_config_singleton(db)
    assert db.rows["config"][0].session_signing_key is not None
    assert len(db.rows["config"][0].session_signing_key) == 32


async def test_run_seeders_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seeders, "FIRST_BOOT_LOG", tmp_path / "fb.log")
    db = FakeSession()
    await run_seeders(db)
    first_users = len(db.rows.get("users", []))
    first_presets = len(db.rows.get("rip_presets", []))
    first_routes = len(db.rows.get("session_routes", []))
    assert first_users == 2 and first_presets >= 1 and first_routes == 2

    # Re-run: every _insert_missing row already exists → continue past each.
    await run_seeders(db)
    assert len(db.rows["users"]) == first_users
    assert len(db.rows["rip_presets"]) == first_presets
    assert len(db.rows["session_routes"]) == first_routes


async def test_run_seeders_corrects_builtin_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Built-ins are clone-to-edit, so the seeder owns their names: a row that
    still carries an older shipped name (e.g. the pre-cleanup em-dash form) is
    renamed on the next boot, without a migration. Custom rows are untouched."""
    monkeypatch.setattr(seeders, "FIRST_BOOT_LOG", tmp_path / "fb.log")
    db = FakeSession()
    await run_seeders(db)
    preset = next(p for p in db.rows["rip_presets"] if p.id == "rpr_builtin_data_copy")
    session_row = next(s for s in db.rows["sessions"] if s.id == "ses_builtin_movie_plex_1080p")
    preset.name = "Data — Copy"
    session_row.name = "Movie → Plex 1080p H.265"

    await run_seeders(db)

    assert preset.name == "Data: Copy"
    assert session_row.name == "Movie to Plex 1080p H.265"
    assert "—" not in "".join(r.name for r in db.rows["rip_presets"] + db.rows["sessions"])
    assert "→" not in "".join(r.name for r in db.rows["rip_presets"] + db.rows["sessions"])


async def test_seed_session_routes_seeds_music_cd_and_wildcard() -> None:
    db = FakeSession()
    await _seed_session_routes(db)
    routes = db.rows["session_routes"]
    assert len(routes) == 2
    assert all(r.media_type == MediaType.MUSIC for r in routes)
    assert all(r.session_id == "ses_builtin_music_flac" for r in routes)
    disc_types = {r.disc_type for r in routes}
    assert disc_types == {DiscType.CD, None}


async def test_seed_session_routes_skips_when_table_not_empty() -> None:
    db = FakeSession()
    db.rows["session_routes"] = [
        SessionRoute(id="srt_custom", media_type=MediaType.MOVIE, disc_type=None, session_id="ses_custom")
    ]
    await _seed_session_routes(db)
    # A user's own route must not be joined by the built-ins on the next boot.
    assert len(db.rows["session_routes"]) == 1


async def test_seed_session_routes_flips_flag_on_fresh_seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """I1: a fresh empty DB seeds the built-ins once and flips
    `session_routes_seeded` true so a later boot's empty table (deliberately
    cleared) does not get reseeded."""
    monkeypatch.setattr(seeders, "FIRST_BOOT_LOG", tmp_path / "fb.log")
    db = FakeSession()
    await run_seeders(db)
    assert len(db.rows["session_routes"]) == 2
    assert db.rows["config"][0].session_routes_seeded is True


async def test_upgraded_install_with_flag_false_and_empty_routes_seeds_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix 76-1: simulates an existing deployment that has been through
    migration 0035 under the corrected (conditional) UPDATE — a config row
    already exists with `session_routes_seeded=False` because
    session_routes was empty at migration time (the seeder never shipped
    for this install, not a deliberate clear). The very next boot's
    `run_seeders` call must seed the built-ins exactly once."""
    monkeypatch.setattr(seeders, "FIRST_BOOT_LOG", tmp_path / "fb.log")
    db = FakeSession()
    db.rows["config"] = [
        Config(
            id=1,
            auto_transcode_on_idle=False,
            auto_rip_on_insert=True,
            block_on_miss=True,
            default_retention_policy=RetentionPolicy.KEEP_FOREVER,
            session_signing_key=b"x" * 32,
            session_routes_seeded=False,
        )
    ]
    db.rows["session_routes"] = []

    await run_seeders(db)

    routes = db.rows["session_routes"]
    assert len(routes) == 2
    assert db.rows["config"][0].session_routes_seeded is True

    # A second boot must not duplicate the routes (flag now true).
    await run_seeders(db)
    assert len(db.rows["session_routes"]) == 2


async def test_delete_all_routes_then_rerun_seeders_stays_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I1: clearing every session route and re-running seeders must not
    resurrect them — the one-shot marker set on the first boot prevents the
    empty-table gate from re-firing."""
    monkeypatch.setattr(seeders, "FIRST_BOOT_LOG", tmp_path / "fb.log")
    db = FakeSession()
    await run_seeders(db)
    assert len(db.rows["session_routes"]) == 2

    # User deliberately deletes both seeded routes.
    db.rows["session_routes"] = []

    await run_seeders(db)
    assert db.rows["session_routes"] == []
