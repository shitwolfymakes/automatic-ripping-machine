"""Minimum title length (config.min_title_length_seconds): env seeding, the config API and the ripper config."""

from __future__ import annotations

import secrets

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arm_backend import min_title_length
from arm_backend.config import settings
from arm_backend.constants import CONFIG_SINGLETON_ID
from arm_backend.db import get_session
from arm_backend.jwt_utils import issue_access_token
from arm_backend.routers import config as config_router
from arm_backend.routers import ripper as ripper_router
from arm_backend.seeders import _seed_config_singleton
from arm_common import Config, RetentionPolicy, User

from tests._fakes import FakeSession


def _config(**kw: object) -> Config:
    return Config(
        id=CONFIG_SINGLETON_ID,
        auto_transcode_on_idle=False,
        auto_rip_on_insert=True,
        block_on_miss=True,
        default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
        notification_apprise_urls=[],
        notifications_enabled=False,
        session_signing_key=b"x" * 32,
        **kw,
    )


@pytest.mark.parametrize(
    ("env", "expected"),
    [("", 120), ("90", 90), (" 300 ", 300), ("0", 0), ("-5", 120), ("abc", 120)],
)
def test_env_seed_reads_the_ripper_min_length_env(monkeypatch: pytest.MonkeyPatch, env: str, expected: int) -> None:
    monkeypatch.setattr(settings, "ARM_RIPPER_MIN_LENGTH_SECONDS", env)
    assert min_title_length.env_min_title_length_seconds() == expected


def test_configured_value_wins_over_the_env_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ARM_RIPPER_MIN_LENGTH_SECONDS", "90")
    assert min_title_length.min_title_length_seconds(_config(min_title_length_seconds=45)) == 45
    assert min_title_length.min_title_length_seconds(_config()) == 90


async def test_fresh_config_singleton_seeds_the_min_title_length_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ARM_RIPPER_MIN_LENGTH_SECONDS", "90")
    db = FakeSession()
    await _seed_config_singleton(db)
    (cfg,) = [r for r in db.added if isinstance(r, Config)]
    assert cfg.min_title_length_seconds == 90


async def test_seed_backfills_an_unseeded_min_title_length_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ARM_RIPPER_MIN_LENGTH_SECONDS", "300")
    db = FakeSession()
    db.rows["config"] = [_config()]
    await _seed_config_singleton(db)
    assert db.rows["config"][0].min_title_length_seconds == 300


async def test_seed_keeps_an_operator_min_title_length(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ARM_RIPPER_MIN_LENGTH_SECONDS", "300")
    db = FakeSession()
    db.rows["config"] = [_config(min_title_length_seconds=60)]
    await _seed_config_singleton(db)
    assert db.rows["config"][0].min_title_length_seconds == 60


def _config_app(db: FakeSession) -> tuple[FastAPI, dict[str, str]]:
    key = secrets.token_bytes(32)
    app = FastAPI()
    app.state.signing_key = key
    app.include_router(config_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )
    token, _ = issue_access_token("usr_admin", "admin", key)
    return app, {"Authorization": f"Bearer {token}"}


def test_config_view_shows_the_min_title_length() -> None:
    db = FakeSession()
    db.rows["config"] = [_config(min_title_length_seconds=75)]
    app, auth = _config_app(db)
    with TestClient(app) as client:
        r = client.get("/api/config", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["min_title_length_seconds"] == 75


@pytest.mark.parametrize("value", [0, 60, 3600])
def test_patch_accepts_a_min_title_length_from_0_to_3600(value: int) -> None:
    db = FakeSession()
    db.rows["config"] = [_config(min_title_length_seconds=120)]
    app, auth = _config_app(db)
    with TestClient(app) as client:
        r = client.patch("/api/config", json={"min_title_length_seconds": value}, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["min_title_length_seconds"] == value
    assert db.rows["config"][0].min_title_length_seconds == value


@pytest.mark.parametrize("value", [-1, 3601, None])
def test_patch_refuses_a_min_title_length_outside_0_to_3600(value: int | None) -> None:
    db = FakeSession()
    db.rows["config"] = [_config(min_title_length_seconds=120)]
    app, auth = _config_app(db)
    with TestClient(app) as client:
        r = client.patch("/api/config", json={"min_title_length_seconds": value}, headers=auth)
    assert r.status_code == 400
    assert r.json()["detail"] == "min_title_length_seconds must be 0 to 3600 seconds"
    assert db.rows["config"][0].min_title_length_seconds == 120


def test_the_field_help_gives_the_range() -> None:
    from arm_common.config_metadata import CONFIG_FIELD_META

    (meta,) = [m for m in CONFIG_FIELD_META if m.key == "min_title_length_seconds"]
    assert "0 to 3600 seconds" in meta.help


def test_ripper_config_carries_the_min_title_length() -> None:
    db = FakeSession()
    db.rows["config"] = [_config(min_title_length_seconds=60)]
    app = FastAPI()
    app.include_router(ripper_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as client:
        r = client.get("/api/ripper/config", headers={"Authorization": "Bearer tok-service"})
    assert r.status_code == 200, r.text
    assert r.json()["min_title_length_seconds"] == 60
