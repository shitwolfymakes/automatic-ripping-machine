"""Session-routes CRUD router tests (G-02/G-17) — list/upsert/delete,
media-type-mismatch 422, non-writer 403. Modeled on test_rip_presets_router.py."""

from __future__ import annotations

import os
import secrets

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import pytest  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import session_routes as session_routes_router  # noqa: E402
from arm_common import DiscType, MediaType, Session, SessionRoute, User  # noqa: E402
from arm_common.models.user import GUEST_ROLE  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _session(session_id: str = "ses_music", media_type: MediaType = MediaType.MUSIC) -> Session:
    return Session(
        id=session_id,
        name="Music -> FLAC",
        media_type=media_type,
        is_builtin=True,
        rip_preset_id="rpr_music",
        output_path_template="{artist}/{album}/{track}.{ext}",
    )


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(session_routes_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    db.rows.setdefault("users", []).extend(
        [
            User(id="usr_admin", username="admin", password_hash="x", password_must_change=False),
            User(
                id="usr_guest",
                username="guest",
                password_hash="x",
                password_must_change=False,
                role=GUEST_ROLE,
                disabled=False,
            ),
        ]
    )
    admin_token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, admin_token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_list_returns_seeded_routes(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["session_routes"] = [
        SessionRoute(id="srt_a", media_type=MediaType.MUSIC, disc_type=DiscType.CD, session_id="ses_music"),
        SessionRoute(id="srt_b", media_type=MediaType.MUSIC, disc_type=None, session_id="ses_music"),
    ]
    with TestClient(app) as client:
        r = client.get("/api/session-routes", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    ids = {row["id"] for row in body}
    assert ids == {"srt_a", "srt_b"}


def test_upsert_creates_new_route(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["sessions"] = [_session()]
    db.rows["session_routes"] = []
    body = {"media_type": "music", "disc_type": "cd", "session_id": "ses_music"}
    with TestClient(app) as client:
        r = client.put("/api/session-routes", json=body, headers=_auth(token))
    assert r.status_code == 200
    out = r.json()
    assert out["media_type"] == "music"
    assert out["disc_type"] == "cd"
    assert out["session_id"] == "ses_music"
    assert len(db.rows["session_routes"]) == 1


def test_upsert_wildcard_disc_type_null(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["sessions"] = [_session()]
    db.rows["session_routes"] = []
    body = {"media_type": "music", "disc_type": None, "session_id": "ses_music"}
    with TestClient(app) as client:
        r = client.put("/api/session-routes", json=body, headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["disc_type"] is None


def test_upsert_updates_existing_route_in_place(signing_key: bytes) -> None:
    """PUTting the same (media_type, disc_type) key twice updates the
    existing row rather than creating a duplicate."""
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["sessions"] = [_session(), _session("ses_music_alt")]
    db.rows["session_routes"] = []
    body1 = {"media_type": "music", "disc_type": "cd", "session_id": "ses_music"}
    body2 = {"media_type": "music", "disc_type": "cd", "session_id": "ses_music_alt"}
    with TestClient(app) as client:
        first = client.put("/api/session-routes", json=body1, headers=_auth(token))
        second = client.put("/api/session-routes", json=body2, headers=_auth(token))
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["session_id"] == "ses_music_alt"
    assert len(db.rows["session_routes"]) == 1


def test_upsert_unknown_session_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["sessions"] = []
    body = {"media_type": "music", "disc_type": "cd", "session_id": "ses_missing"}
    with TestClient(app) as client:
        r = client.put("/api/session-routes", json=body, headers=_auth(token))
    assert r.status_code == 404
    assert "unknown session_id" in r.json()["detail"]


def test_upsert_media_type_mismatch_422(signing_key: bytes) -> None:
    """A tv route pointing at a music session is a config error: tv and
    music are never compatible in either direction."""
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["sessions"] = [_session(media_type=MediaType.MUSIC)]
    body = {"media_type": "tv", "disc_type": None, "session_id": "ses_music"}
    with TestClient(app) as client:
        r = client.put("/api/session-routes", json=body, headers=_auth(token))
    assert r.status_code == 422
    assert "media_type" in r.json()["detail"]
    assert "not compatible with" in r.json()["detail"]


def test_upsert_movie_route_to_iso_session_accepted(signing_key: bytes) -> None:
    """A movie route pointing at an iso-dump session is expressible: an
    iso/data session consumes a dump of any video disc, matching what the
    apply path (_media_types_compatible) already allows."""
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["sessions"] = [_session(session_id="ses_iso", media_type=MediaType.ISO)]
    body = {"media_type": "movie", "disc_type": None, "session_id": "ses_iso"}
    with TestClient(app) as client:
        r = client.put("/api/session-routes", json=body, headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["session_id"] == "ses_iso"


def test_upsert_movie_route_to_tv_session_accepted(signing_key: bytes) -> None:
    """movie and tv are the same track kind — a movie route to a tv session
    (or vice versa) is a compatible pairing, not a config error."""
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["sessions"] = [_session(session_id="ses_tv", media_type=MediaType.TV)]
    body = {"media_type": "movie", "disc_type": None, "session_id": "ses_tv"}
    with TestClient(app) as client:
        r = client.put("/api/session-routes", json=body, headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["session_id"] == "ses_tv"


def test_upsert_movie_route_to_music_session_still_422(signing_key: bytes) -> None:
    """Music stays strictly music: a movie route to a music session is still
    a hard config error even under the relaxed compatibility check."""
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["sessions"] = [_session(session_id="ses_music_2", media_type=MediaType.MUSIC)]
    body = {"media_type": "movie", "disc_type": None, "session_id": "ses_music_2"}
    with TestClient(app) as client:
        r = client.put("/api/session-routes", json=body, headers=_auth(token))
    assert r.status_code == 422


def test_upsert_requires_writer_403(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["sessions"] = [_session()]
    guest_token, _ = issue_access_token("usr_guest", "guest", signing_key)
    body = {"media_type": "music", "disc_type": "cd", "session_id": "ses_music"}
    with TestClient(app) as client:
        r = client.put("/api/session-routes", json=body, headers=_auth(guest_token))
    assert r.status_code == 403


def test_delete_success_204(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["session_routes"] = [
        SessionRoute(id="srt_del", media_type=MediaType.MUSIC, disc_type=DiscType.CD, session_id="ses_music")
    ]
    with TestClient(app) as client:
        r = client.delete("/api/session-routes/srt_del", headers=_auth(token))
    assert r.status_code == 204
    assert db.rows["session_routes"] == []


def test_delete_unknown_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["session_routes"] = []
    with TestClient(app) as client:
        r = client.delete("/api/session-routes/srt_missing", headers=_auth(token))
    assert r.status_code == 404


def test_delete_requires_writer_403(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["session_routes"] = [
        SessionRoute(id="srt_a", media_type=MediaType.MUSIC, disc_type=DiscType.CD, session_id="ses_music")
    ]
    guest_token, _ = issue_access_token("usr_guest", "guest", signing_key)
    with TestClient(app) as client:
        r = client.delete("/api/session-routes/srt_a", headers=_auth(guest_token))
    assert r.status_code == 403
