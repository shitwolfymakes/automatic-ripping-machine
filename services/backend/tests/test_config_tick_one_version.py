"""`config.tick_one_version` on the config API: the view default and the PATCH round trip."""

from __future__ import annotations

import secrets

import pytest
from fastapi.testclient import TestClient

from tests.test_config_iso_rips import _auth, _make_app, _patch, _row, _seed
from tests._fakes import FakeSession


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def test_the_default_is_one_version_per_film(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/config", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["tick_one_version"] is True


def test_patch_turns_it_off_and_on(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        off = _patch(client, token, {"tick_one_version": False})
        assert off.status_code == 200, off.text  # type: ignore[attr-defined]
        assert off.json()["tick_one_version"] is False  # type: ignore[attr-defined]
        assert _row(db).tick_one_version is False
        on = _patch(client, token, {"tick_one_version": True})
        assert on.json()["tick_one_version"] is True  # type: ignore[attr-defined]
