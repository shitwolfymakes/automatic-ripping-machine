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
    run_seeders,
)
from arm_common import Config, RetentionPolicy, User  # noqa: E402

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
    assert first_users == 2 and first_presets >= 1

    # Re-run: every _insert_missing row already exists → continue past each.
    await run_seeders(db)
    assert len(db.rows["users"]) == first_users
    assert len(db.rows["rip_presets"]) == first_presets


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
