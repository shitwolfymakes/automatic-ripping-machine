"""First-run setup walkthrough against the real booted app (setup spec 2026-10-01):
public status, the must-change gate's read-only setup GETs, the password step,
progress, completion."""

from __future__ import annotations


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_fresh_install_walks_setup(app_client: object) -> None:
    c = app_client
    assert c.get("/api/setup/status").json()["first_run"] is True  # type: ignore[attr-defined]

    login = c.post("/api/auth/login", json={"username": "admin", "password": "admin"}).json()  # type: ignore[attr-defined]
    h = _h(login["access_token"])

    # Step 1 can render before the password is changed ...
    view = c.get("/api/setup", headers=h)  # type: ignore[attr-defined]
    assert view.status_code == 200, view.text
    assert view.json()["admin_default_password"] is True
    assert view.json()["current_step"] == "account"
    assert c.get("/api/system/version", headers=h).status_code == 200  # type: ignore[attr-defined]
    assert c.get("/api/system/resources", headers=h).status_code == 200  # type: ignore[attr-defined]
    # ... but nothing can be written until it is.
    assert c.put("/api/setup/steps/system", json={"state": "done"}, headers=h).status_code == 403  # type: ignore[attr-defined]

    changed = c.post(  # type: ignore[attr-defined]
        "/api/auth/password", json={"current_password": "admin", "new_password": "e2e-setup-pw"}, headers=h
    )
    assert changed.status_code == 200, changed.text
    relog = c.post("/api/auth/login", json={"username": "admin", "password": "e2e-setup-pw"})  # type: ignore[attr-defined]
    h = _h(relog.json()["access_token"])

    view = c.get("/api/setup", headers=h).json()  # type: ignore[attr-defined]
    assert view["progress"]["account"]["state"] == "done"
    assert view["current_step"] == "system"

    put = c.put("/api/setup/steps/system", json={"state": "attention"}, headers=h)  # type: ignore[attr-defined]
    assert put.status_code == 200, put.text
    assert put.json()["current_step"] == "drives"

    routes = c.get("/api/setup/disc-routes", headers=h)  # type: ignore[attr-defined]
    assert routes.status_code == 200, routes.text
    assert [r["kind"] for r in routes.json()] == ["movie", "tv", "music", "data", "iso"]

    done = c.post("/api/setup/complete", headers=h).json()  # type: ignore[attr-defined]
    assert done["completed_at"] is not None
    assert c.get("/api/setup/status").json()["first_run"] is False  # type: ignore[attr-defined]

    again = c.post("/api/setup/restart", headers=h).json()  # type: ignore[attr-defined]
    assert again["completed_at"] is None
    assert c.get("/api/setup/status").json()["first_run"] is True  # type: ignore[attr-defined]
