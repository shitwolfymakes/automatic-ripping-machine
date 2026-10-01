"""`/api/iso` router: library listing, create rip, cancel rip."""

from __future__ import annotations

import asyncio
import os
import secrets
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend import file_browser as fb  # noqa: E402
from arm_backend.config import settings  # noqa: E402
from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.ripper_manager import RipperManagerError  # noqa: E402
from arm_backend.routers import iso as iso_router  # noqa: E402
from arm_backend.seeders import CONFIG_SINGLETON_ID  # noqa: E402
from arm_common import (  # noqa: E402
    Config,
    Drive,
    DriveKind,
    DriveLifecycle,
    DriveSourceKind,
    DriveStatus,
    Job,
    JobStatus,
    MediaType,
    Session,
    User,
)
from arm_common.models.user import GUEST_ROLE  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

# Captured at import, before any fixture swaps the registry out (same idiom
# as test_files_router.py's `_REAL_ISO_ROOT`).
_REAL_ISO_ROOT = fb.ROOTS["ISO"]


class _YieldingFakeSession(FakeSession):
    """`FakeSession.execute` never actually suspends (tests/_fakes.py has no
    real I/O to await), so two concurrent `create_iso_rip` calls against a
    plain `FakeSession` never interleave at all: the first just runs to
    completion — through its own `asyncio.to_thread(ensure_running)` — before
    the second's coroutine is ever scheduled, which would make
    `test_create_is_serialised` pass even with `_create_lock` gutted to a
    no-op. Only used by that test: a real forced suspension point before
    every read, so both requests can genuinely race to read `live` before
    either commits — which is exactly what `_create_lock` must prevent."""

    async def execute(self, stmt: Any) -> Any:
        await asyncio.sleep(0)
        return await super().execute(stmt)


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


class _Hub:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(
        self,
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        persist: bool = True,
        job_id: str | None = None,
        track_id: str | None = None,
        session: Any = None,
    ) -> None:
        self.events.append({"topic": topic, "event_type": event_type, "payload": payload})


class _StubManager:
    """Records `ensure_running` / `remove` calls; raises when told to.
    `container_statuses` (the sweep `create_iso_rip` runs first) reports
    every container "running" unless `states` says otherwise."""

    def __init__(
        self,
        *,
        ensure_fail: str | None = None,
        remove_fail: str | None = None,
        states: dict[str, str] | None = None,
    ) -> None:
        self.ensure_fail = ensure_fail
        self.remove_fail = remove_fail
        self.states = states or {}
        self.ensured: list[str] = []
        self.removed: list[str] = []

    def container_statuses(self, drive_ids: Any) -> dict[str, tuple[str, None]]:
        return {i: (self.states.get(i, "running"), None) for i in drive_ids}

    def ensure_running(self, drive: Drive) -> str:
        if self.ensure_fail:
            raise RipperManagerError(self.ensure_fail)
        self.ensured.append(drive.id)
        return "arm-ripper-test"

    def remove(self, drive_id: str) -> int:
        if self.remove_fail:
            raise RipperManagerError(self.remove_fail)
        self.removed.append(drive_id)
        return 1


@pytest.fixture
def lib(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A configured ISO library at `tmp_path/lib`: `fb.ROOTS["ISO"]` AND
    `settings.ISO_INGRESS_ROOT`/`ARM_HOST_ISO_LIBRARY_PATH` all point at it
    (the router + `iso_rips` read settings directly; `file_browser` reads
    the roots registry)."""
    path = tmp_path / "lib"
    path.mkdir()
    monkeypatch.setitem(fb.ROOTS, "ISO", _REAL_ISO_ROOT.model_copy(update={"path": str(path)}))
    monkeypatch.setattr(settings, "ISO_INGRESS_ROOT", str(path))
    monkeypatch.setattr(settings, "ARM_HOST_ISO_LIBRARY_PATH", "/mnt/nas/iso")
    return path


def _build_app(db: FakeSession, signing_key: bytes, manager: _StubManager, hub: _Hub | None = None) -> FastAPI:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.ripper_manager = manager
    app.state.ws_hub = hub or _Hub()
    app.include_router(iso_router.router)

    async def _s() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _s
    return app


def _admin_token(db: FakeSession, signing_key: bytes) -> str:
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return token


def _reader_token(db: FakeSession, signing_key: bytes) -> str:
    db.rows.setdefault("users", []).append(
        User(id="usr_reader", username="reader", password_hash="x", password_must_change=False, role=GUEST_ROLE)
    )
    token, _ = issue_access_token("usr_reader", "reader", signing_key)
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _virtual(
    drive_id: str = "drv_iso1",
    *,
    lifecycle: DriveLifecycle = DriveLifecycle.ENROLLED,
    source_path: str = "Movies/x.iso",
) -> Drive:
    return Drive(
        id=drive_id,
        hostname=f"iso-{drive_id}",
        device_path="/source/x.iso",
        status=DriveStatus.ONLINE,
        lifecycle=lifecycle,
        kind=DriveKind.VIRTUAL,
        source_kind=DriveSourceKind.ISO,
        source_path=source_path,
    )


def _optical(drive_id: str = "drv_sr0") -> Drive:
    return Drive(
        id=drive_id,
        hostname=f"scan-{drive_id}",
        device_path="/dev/sr0",
        status=DriveStatus.ONLINE,
        lifecycle=DriveLifecycle.ENROLLED,
    )


# --- library listing -----------------------------------------------------


def test_library_lists_folders_then_isos_hides_others(lib: Path, signing_key: bytes) -> None:
    (lib / "Movies").mkdir()
    (lib / "b.iso").write_bytes(b"x")
    (lib / "a.iso").write_bytes(b"x")
    (lib / "notes.txt").write_text("x")
    (lib / "UPPER.ISO").write_bytes(b"x")
    db = FakeSession()
    token = _admin_token(db, signing_key)
    app = _build_app(db, signing_key, _StubManager())
    with TestClient(app) as client:
        body = client.get("/api/iso/library", headers=_auth(token)).json()
    assert [(e["name"], e["kind"]) for e in body["entries"]] == [
        ("Movies", "folder"),
        ("a.iso", "iso"),
        ("b.iso", "iso"),
    ]
    assert body["host_path"] == "/mnt/nas/iso"


def test_library_marks_ripping(lib: Path, signing_key: bytes) -> None:
    (lib / "a.iso").write_bytes(b"x")
    db = FakeSession()
    db.rows["drives"] = [_virtual(source_path="a.iso")]
    token = _admin_token(db, signing_key)
    app = _build_app(db, signing_key, _StubManager())
    with TestClient(app) as client:
        body = client.get("/api/iso/library", headers=_auth(token)).json()
    entry = next(e for e in body["entries"] if e["name"] == "a.iso")
    assert entry["ripping"] is True


def test_library_503_when_env_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, signing_key: bytes) -> None:
    path = tmp_path / "lib"
    path.mkdir()
    monkeypatch.setitem(fb.ROOTS, "ISO", _REAL_ISO_ROOT.model_copy(update={"path": str(path)}))
    monkeypatch.setattr(settings, "ISO_INGRESS_ROOT", str(path))
    monkeypatch.setattr(settings, "ARM_HOST_ISO_LIBRARY_PATH", "")
    db = FakeSession()
    token = _admin_token(db, signing_key)
    app = _build_app(db, signing_key, _StubManager())
    with TestClient(app) as client:
        r = client.get("/api/iso/library", headers=_auth(token))
    assert r.status_code == 503


def test_library_404_missing_subpath(lib: Path, signing_key: bytes) -> None:
    db = FakeSession()
    token = _admin_token(db, signing_key)
    app = _build_app(db, signing_key, _StubManager())
    with TestClient(app) as client:
        r = client.get("/api/iso/library", params={"subpath": "Nope"}, headers=_auth(token))
    assert r.status_code == 404, r.text


def test_library_400_when_subpath_escapes(lib: Path, signing_key: bytes) -> None:
    db = FakeSession()
    token = _admin_token(db, signing_key)
    app = _build_app(db, signing_key, _StubManager())
    with TestClient(app) as client:
        r = client.get("/api/iso/library", params={"subpath": "../x"}, headers=_auth(token))
    assert r.status_code == 400, r.text


def test_library_503_when_mount_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, signing_key: bytes) -> None:
    absent = tmp_path / "absent"
    monkeypatch.setitem(fb.ROOTS, "ISO", _REAL_ISO_ROOT.model_copy(update={"path": str(absent)}))
    monkeypatch.setattr(settings, "ISO_INGRESS_ROOT", str(absent))
    monkeypatch.setattr(settings, "ARM_HOST_ISO_LIBRARY_PATH", "/mnt/nas/iso")
    db = FakeSession()
    token = _admin_token(db, signing_key)
    app = _build_app(db, signing_key, _StubManager())
    with TestClient(app) as client:
        r = client.get("/api/iso/library", headers=_auth(token))
    assert r.status_code == 503


# --- create ----------------------------------------------------------------


def test_create_503_when_not_configured(signing_key: bytes) -> None:
    """No `lib` fixture here: the library is unconfigured (the real default,
    an empty `ARM_HOST_ISO_LIBRARY_PATH`)."""
    db = FakeSession()
    token = _admin_token(db, signing_key)
    app = _build_app(db, signing_key, _StubManager())
    with TestClient(app) as client:
        r = client.post("/api/iso/rips", json={"path": "x.iso"}, headers=_auth(token))
    assert r.status_code == 503, r.text


def test_manager_unavailable_503(lib: Path, signing_key: bytes) -> None:
    (lib / "x.iso").write_bytes(b"x")
    db = FakeSession()
    token = _admin_token(db, signing_key)
    app = _build_app(db, signing_key, _StubManager())
    app.state.ripper_manager = None
    with TestClient(app) as client:
        r = client.post("/api/iso/rips", json={"path": "x.iso"}, headers=_auth(token))
    assert r.status_code == 503, r.text


@pytest.mark.parametrize("path", ["../x.iso", "/etc/x.iso", "Movies/../../x.iso", "link_out.iso"])
def test_create_rejects_escapes(lib: Path, signing_key: bytes, path: str) -> None:
    outside = lib.parent / "outside.iso"
    outside.write_bytes(b"x")
    (lib / "link_out.iso").symlink_to(outside)
    db = FakeSession()
    token = _admin_token(db, signing_key)
    manager = _StubManager()
    app = _build_app(db, signing_key, manager)
    with TestClient(app) as client:
        r = client.post("/api/iso/rips", json={"path": path}, headers=_auth(token))
    assert r.status_code == 400, r.text
    assert manager.ensured == []
    assert db.rows.get("drives", []) == []


@pytest.mark.parametrize("name", ["notes.txt", "UPPER.ISO", "Movies"])
def test_create_rejects_non_iso(lib: Path, signing_key: bytes, name: str) -> None:
    if name == "Movies":
        (lib / name).mkdir()
    else:
        (lib / name).write_bytes(b"x")
    db = FakeSession()
    token = _admin_token(db, signing_key)
    manager = _StubManager()
    app = _build_app(db, signing_key, manager)
    with TestClient(app) as client:
        r = client.post("/api/iso/rips", json={"path": name}, headers=_auth(token))
    assert r.status_code == 400, r.text
    assert manager.ensured == []


def test_create_404_missing_and_unknown_session(lib: Path, signing_key: bytes) -> None:
    (lib / "Movies").mkdir()
    (lib / "Movies" / "x.iso").write_bytes(b"x")
    db = FakeSession()
    token = _admin_token(db, signing_key)
    manager = _StubManager()
    app = _build_app(db, signing_key, manager)
    with TestClient(app) as client:
        r = client.post("/api/iso/rips", json={"path": "Movies/missing.iso"}, headers=_auth(token))
        assert r.status_code == 404, r.text
        assert "no such ISO file" in r.json()["detail"]

        r = client.post(
            "/api/iso/rips",
            json={"path": "Movies/x.iso", "session_id": "ses_nope"},
            headers=_auth(token),
        )
        assert r.status_code == 404, r.text
        assert "unknown session" in r.json()["detail"]


def test_create_spawns_virtual_drive(lib: Path, signing_key: bytes) -> None:
    (lib / "Movies").mkdir()
    (lib / "Movies" / "x.iso").write_bytes(b"x")
    db = FakeSession()
    sess = Session(
        id="ses_1",
        name="Movies",
        media_type=MediaType.MOVIE,
        is_builtin=False,
        rip_preset_id="rpr_1",
        output_path_template="{title}",
    )
    db.rows["sessions"] = [sess]
    token = _admin_token(db, signing_key)
    manager = _StubManager()
    app = _build_app(db, signing_key, manager)
    with TestClient(app) as client:
        r = client.post("/api/iso/rips", json={"path": "Movies/x.iso", "session_id": sess.id}, headers=_auth(token))
    assert r.status_code == 201, r.text
    d = db.rows["drives"][-1]
    assert (d.kind, d.lifecycle, d.source_kind, d.source_path) == (
        DriveKind.VIRTUAL,
        DriveLifecycle.ENROLLED,
        DriveSourceKind.ISO,
        "Movies/x.iso",
    )
    assert d.device_path == "/source/x.iso"
    assert d.display_name == "x.iso"
    assert d.rip_params_json["session_id"] == sess.id
    assert manager.ensured == [d.id]
    assert r.json()["drive_id"] == d.id


def test_create_409_when_cap_full(lib: Path, signing_key: bytes) -> None:
    (lib / "Movies").mkdir()
    (lib / "Movies" / "x.iso").write_bytes(b"x")
    db = FakeSession()
    db.rows["config"] = [Config(id=CONFIG_SINGLETON_ID, max_parallel_iso_rips=1)]
    db.rows["drives"] = [_virtual(source_path="Movies/other.iso")]
    token = _admin_token(db, signing_key)
    manager = _StubManager()
    app = _build_app(db, signing_key, manager)
    with TestClient(app) as client:
        r = client.post("/api/iso/rips", json={"path": "Movies/x.iso"}, headers=_auth(token))
    assert r.status_code == 409, r.text
    assert "limit is reached" in r.json()["detail"]
    assert manager.ensured == []


def test_create_sweeps_a_finished_rip_before_the_cap_check(lib: Path, signing_key: bytes) -> None:
    """M1: the last rip's container has exited but the 30 s watchdog has not
    run yet. Create sweeps first, so the finished drive is retired and no
    longer fills the default cap of 1."""
    (lib / "Movies").mkdir()
    (lib / "Movies" / "x.iso").write_bytes(b"x")
    db = FakeSession()
    db.rows["config"] = [Config(id=CONFIG_SINGLETON_ID, max_parallel_iso_rips=1)]
    old = _virtual("drv_old", source_path="Movies/x.iso")  # same ISO: not a duplicate either
    db.rows["drives"] = [old]
    db.rows["jobs"] = [Job(id="job_old", drive_id="drv_old", status=JobStatus.RIPPED)]
    token = _admin_token(db, signing_key)
    manager = _StubManager(states={"drv_old": "exited"})
    app = _build_app(db, signing_key, manager)
    with TestClient(app) as client:
        r = client.post("/api/iso/rips", json={"path": "Movies/x.iso"}, headers=_auth(token))
    assert r.status_code == 201, r.text
    assert old.lifecycle is DriveLifecycle.RETIRED
    assert manager.removed == ["drv_old"]
    assert manager.ensured == [r.json()["drive_id"]]


def test_create_409_while_ripping_is_paused(lib: Path, signing_key: bytes) -> None:
    """I4: the ripper's identify would be refused while paused, leaving a
    retired drive and no job. Refuse up front with the manual-trigger wording."""
    (lib / "Movies").mkdir()
    (lib / "Movies" / "x.iso").write_bytes(b"x")
    db = FakeSession()
    db.rows["config"] = [Config(id=CONFIG_SINGLETON_ID, ripping_paused=True, hold_for_review=False)]
    token = _admin_token(db, signing_key)
    manager = _StubManager()
    app = _build_app(db, signing_key, manager)
    with TestClient(app) as client:
        r = client.post("/api/iso/rips", json={"path": "Movies/x.iso"}, headers=_auth(token))
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "ripping is paused; no new jobs accepted"
    assert manager.ensured == []
    assert "drives" not in db.rows


def test_create_409_when_already_ripping(lib: Path, signing_key: bytes) -> None:
    (lib / "Movies").mkdir()
    (lib / "Movies" / "x.iso").write_bytes(b"x")
    db = FakeSession()
    db.rows["config"] = [Config(id=CONFIG_SINGLETON_ID, max_parallel_iso_rips=8)]
    db.rows["drives"] = [_virtual(source_path="Movies/x.iso")]
    token = _admin_token(db, signing_key)
    manager = _StubManager()
    app = _build_app(db, signing_key, manager)
    with TestClient(app) as client:
        r = client.post("/api/iso/rips", json={"path": "Movies/x.iso"}, headers=_auth(token))
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "This ISO is already being ripped."
    assert manager.ensured == []


async def test_create_is_serialised(lib: Path, signing_key: bytes) -> None:
    (lib / "Movies").mkdir()
    (lib / "Movies" / "x.iso").write_bytes(b"x")
    db = _YieldingFakeSession()
    token = _admin_token(db, signing_key)
    manager = _StubManager()
    app = _build_app(db, signing_key, manager)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r1, r2 = await asyncio.gather(
            client.post("/api/iso/rips", json={"path": "Movies/x.iso"}, headers=_auth(token)),
            client.post("/api/iso/rips", json={"path": "Movies/x.iso"}, headers=_auth(token)),
        )
    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [201, 409], (r1.status_code, r1.text, r2.status_code, r2.text)
    assert len(manager.ensured) == 1
    assert len(db.rows.get("drives", [])) == 1


def test_create_spawn_failure_retires_and_500(lib: Path, signing_key: bytes) -> None:
    (lib / "Movies").mkdir()
    (lib / "Movies" / "x.iso").write_bytes(b"x")
    db = FakeSession()
    token = _admin_token(db, signing_key)
    manager = _StubManager(ensure_fail="APIError: boom")
    app = _build_app(db, signing_key, manager)
    with TestClient(app) as client:
        r = client.post("/api/iso/rips", json={"path": "Movies/x.iso"}, headers=_auth(token))
    assert r.status_code == 500, r.text
    assert "could not start the ISO ripper" in r.json()["detail"]
    d = db.rows["drives"][-1]
    assert d.lifecycle is DriveLifecycle.RETIRED
    assert manager.removed == [d.id]


# --- cancel ------------------------------------------------------------------


def test_cancel_abandons_and_retires(signing_key: bytes) -> None:
    db = FakeSession()
    drive = _virtual()
    db.rows["drives"] = [drive]
    db.rows["jobs"] = [Job(id="job_1", drive_id=drive.id, status=JobStatus.AWAITING_REVIEW)]
    token = _admin_token(db, signing_key)
    manager = _StubManager()
    hub = _Hub()
    app = _build_app(db, signing_key, manager, hub)
    with TestClient(app) as client:
        r = client.delete(f"/api/iso/rips/{drive.id}", headers=_auth(token))
    assert r.status_code == 204, r.text
    job = db.rows["jobs"][0]
    assert job.status is JobStatus.ABANDONED
    types = {e["event_type"] for e in hub.events}
    assert {"job.abandoned", "rip.abandoned"} <= types
    assert drive.lifecycle is DriveLifecycle.RETIRED
    assert manager.removed == [drive.id]


@pytest.mark.parametrize("make_drive", [lambda: _virtual(lifecycle=DriveLifecycle.RETIRED), lambda: _optical()])
def test_cancel_refuses_retired_and_optical(signing_key: bytes, make_drive) -> None:
    db = FakeSession()
    drive = make_drive()
    lifecycle_before = drive.lifecycle
    db.rows["drives"] = [drive]
    token = _admin_token(db, signing_key)
    manager = _StubManager()
    app = _build_app(db, signing_key, manager)
    with TestClient(app) as client:
        r = client.delete(f"/api/iso/rips/{drive.id}", headers=_auth(token))
    assert r.status_code == 409, r.text
    assert manager.removed == []
    assert drive.lifecycle is lifecycle_before


def test_cancel_404_unknown_drive(signing_key: bytes) -> None:
    db = FakeSession()
    token = _admin_token(db, signing_key)
    app = _build_app(db, signing_key, _StubManager())
    with TestClient(app) as client:
        r = client.delete("/api/iso/rips/drv_nope", headers=_auth(token))
    assert r.status_code == 404, r.text


def test_cancel_with_no_job_just_retires(signing_key: bytes) -> None:
    """No job row at all (the scan failed before one was created): cancel
    still retires the drive, with no abandon events."""
    db = FakeSession()
    drive = _virtual()
    db.rows["drives"] = [drive]
    token = _admin_token(db, signing_key)
    manager = _StubManager()
    hub = _Hub()
    app = _build_app(db, signing_key, manager, hub)
    with TestClient(app) as client:
        r = client.delete(f"/api/iso/rips/{drive.id}", headers=_auth(token))
    assert r.status_code == 204, r.text
    assert drive.lifecycle is DriveLifecycle.RETIRED
    assert manager.removed == [drive.id]
    assert hub.events == []


# --- authz -------------------------------------------------------------------


def test_reader_cannot_create_or_cancel(lib: Path, signing_key: bytes) -> None:
    (lib / "Movies").mkdir()
    (lib / "Movies" / "x.iso").write_bytes(b"x")
    db = FakeSession()
    db.rows["drives"] = [_virtual()]
    token = _reader_token(db, signing_key)
    app = _build_app(db, signing_key, _StubManager())
    with TestClient(app) as client:
        r = client.post("/api/iso/rips", json={"path": "Movies/x.iso"}, headers=_auth(token))
        assert r.status_code == 403, r.text
        r = client.delete("/api/iso/rips/drv_iso1", headers=_auth(token))
        assert r.status_code == 403, r.text
