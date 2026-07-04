"""End-to-end smoke tests against the real booted app.

These prove the harness works and, as a side effect, cover the wiring that
the fake-session per-router tests structurally cannot reach: `main.py`
(lifespan + router assembly), `db.py` (engine/session), `seeders.py`, and
the real `require_jwt` user-loading auth path.
"""

from __future__ import annotations


def test_health_no_auth(app_client: object) -> None:
    resp = app_client.get("/api/health")  # type: ignore[attr-defined]
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_login_flow_and_must_change_gate(app_client: object) -> None:
    """Seeded admin can log in but is 403'd off normal routes until the
    password is changed (the real must-change enforcement in `require_jwt`)."""
    login = app_client.post(  # type: ignore[attr-defined]
        "/api/auth/login",
        json={"username": "admin", "password": "admin"},
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["password_must_change"] is True
    token = body["access_token"]

    gated = app_client.get(  # type: ignore[attr-defined]
        "/api/diagnostics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert gated.status_code == 403


def test_login_rejects_bad_credentials(app_client: object) -> None:
    resp = app_client.post(  # type: ignore[attr-defined]
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_diagnostics_requires_auth(app_client: object) -> None:
    assert app_client.get("/api/diagnostics").status_code == 401  # type: ignore[attr-defined]


def test_diagnostics_after_password_change(app_client: object, admin_token: str) -> None:
    resp = app_client.get(  # type: ignore[attr-defined]
        "/api/diagnostics",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    names = [s["name"] for s in resp.json()["services"]]
    assert "arm-backend" in names


def test_transcode_presets_seeded_and_listable(app_client: object, admin_token: str) -> None:
    """Covers the previously 0%-coverage transcode_presets router end to end,
    against rows the real seeders inserted."""
    resp = app_client.get(  # type: ignore[attr-defined]
        "/api/transcode-presets",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    presets = resp.json()
    assert isinstance(presets, list) and len(presets) >= 1


def test_transcodes_list_empty(app_client: object, admin_token: str) -> None:
    """Covers the previously 0%-coverage transcodes router; no transcode
    tasks exist on a fresh DB."""
    resp = app_client.get(  # type: ignore[attr-defined]
        "/api/transcodes",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_lifespan_self_registers_backend_host(app_client: object) -> None:
    """The real lifespan (booted by the `app_client` fixture) must set
    `app.state.host_snapshots` / `app.state.hostname` and UPSERT a `hosts`
    row with role="backend" — this is the only tier that exercises the real
    lifespan end to end (see conftest.py's harness docstring)."""
    import arm_backend.main as main_mod
    from arm_backend.host_snapshots import HostSnapshotStore

    app = main_mod.app
    assert isinstance(app.state.host_snapshots, HostSnapshotStore)
    assert app.state.hostname

    from sqlmodel import select

    from arm_common import Host

    async def _fetch_hosts() -> list[Host]:
        async with main_mod.SessionLocal() as session:
            return list((await session.execute(select(Host))).scalars().all())

    hosts = app_client.portal.call(_fetch_hosts)  # type: ignore[attr-defined]
    assert any(h.role == "backend" and h.hostname == app.state.hostname for h in hosts)
