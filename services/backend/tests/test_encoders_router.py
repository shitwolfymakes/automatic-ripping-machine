"""GET /api/encoders: the catalog (`arm_common.encoders.ENCODERS`) with
server-computed availability from the live `gpus` inventory."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import secrets  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import encoders as encoders_router  # noqa: E402
from arm_backend.transcode_dispatcher import TranscodeDispatcher, set_active_dispatcher  # noqa: E402
from arm_backend.ws import WSHub  # noqa: E402
from arm_common import Gpu, User  # noqa: E402
from arm_common.encoders import ENCODERS  # noqa: E402
from arm_common.enums import GpuStatus, GpuVendor  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


def _gpu(gpu_id: str = "gpu_1", vendor: GpuVendor = GpuVendor.QSV, **kw: object) -> Gpu:
    defaults: dict = {
        "id": gpu_id,
        "vendor": vendor,
        "device_path": "/dev/dri/renderD128",
        "encoder_kinds": ["h264", "h265"],
        "status": GpuStatus.AVAILABLE,
        "enabled": True,
        "probed_at": datetime(2026, 9, 26, 12, 0, tzinfo=UTC),
    }
    defaults.update(kw)
    return Gpu(**defaults)


def _app(gpus: list[Gpu]) -> tuple[FastAPI, str]:
    key = secrets.token_bytes(32)
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["gpus"] = gpus

    app = FastAPI()
    app.state.signing_key = key
    app.include_router(encoders_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", key)
    return app, token


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_returns_full_catalog_in_catalog_order() -> None:
    app, token = _app([])
    with TestClient(app) as c:
        r = c.get("/api/encoders", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert [e["id"] for e in body] == list(ENCODERS.keys())


def test_preset_and_cpu_kinds_are_always_available() -> None:
    app, token = _app([])
    with TestClient(app) as c:
        r = c.get("/api/encoders", headers=_auth(token))
    by_id = {e["id"]: e for e in r.json()}

    preset = by_id["preset"]
    assert preset["group"] == "preset"
    assert preset["available"] is True
    assert preset["reason"] is None

    cpu = by_id["cpu_h265"]
    assert cpu["group"] == "cpu"
    assert cpu["available"] is True
    assert cpu["reason"] is None


def test_any_kind_available_but_explains_cpu_fallback_with_no_gpu_rows() -> None:
    app, token = _app([])
    with TestClient(app) as c:
        r = c.get("/api/encoders", headers=_auth(token))
    by_id = {e["id"]: e for e in r.json()}

    any_h265 = by_id["any_h265"]
    assert any_h265["group"] == "any"
    assert any_h265["available"] is True
    assert any_h265["reason"] == "no verified GPU; runs on the CPU"


def test_any_kind_no_reason_once_a_device_is_eligible() -> None:
    app, token = _app([_gpu(vendor=GpuVendor.NVENC)])
    with TestClient(app) as c:
        r = c.get("/api/encoders", headers=_auth(token))
    by_id = {e["id"]: e for e in r.json()}

    any_h265 = by_id["any_h265"]
    assert any_h265["available"] is True
    assert any_h265["reason"] is None


def test_gpu_kind_unavailable_with_no_eligible_device() -> None:
    app, token = _app([])
    with TestClient(app) as c:
        r = c.get("/api/encoders", headers=_auth(token))
    by_id = {e["id"]: e for e in r.json()}

    qsv = by_id["qsv_h265"]
    assert qsv["group"] == "qsv"
    assert qsv["vendor"] == "qsv"
    assert qsv["codec"] == "h265"
    assert qsv["available"] is False
    assert qsv["reason"] == "no enabled device has verified qsv_h265"


def test_gpu_kind_available_with_eligible_device() -> None:
    app, token = _app([_gpu(vendor=GpuVendor.QSV)])
    with TestClient(app) as c:
        r = c.get("/api/encoders", headers=_auth(token))
    by_id = {e["id"]: e for e in r.json()}

    qsv = by_id["qsv_h265"]
    assert qsv["available"] is True
    assert qsv["reason"] is None


def test_gpu_kind_ignores_device_of_a_different_vendor() -> None:
    app, token = _app([_gpu(vendor=GpuVendor.NVENC)])
    with TestClient(app) as c:
        r = c.get("/api/encoders", headers=_auth(token))
    by_id = {e["id"]: e for e in r.json()}

    qsv = by_id["qsv_h265"]
    assert qsv["available"] is False

    nvenc = by_id["nvenc_h265"]
    assert nvenc["available"] is True


def test_gpu_kind_ignores_disabled_or_unprobed_device() -> None:
    app, token = _app([_gpu(vendor=GpuVendor.VAAPI, enabled=False)])
    with TestClient(app) as c:
        r = c.get("/api/encoders", headers=_auth(token))
    by_id = {e["id"]: e for e in r.json()}

    assert by_id["vaapi_h265"]["available"] is False


def test_vaapi_group_is_vendor_value() -> None:
    app, token = _app([])
    with TestClient(app) as c:
        r = c.get("/api/encoders", headers=_auth(token))
    by_id = {e["id"]: e for e in r.json()}
    assert by_id["vaapi_h264"]["group"] == "vaapi"
    assert by_id["nvenc_h264"]["group"] == "nvenc"


def _awaiting_dispatcher(gpu_id: str, *, probing: bool) -> TranscodeDispatcher:
    disp = TranscodeDispatcher(MagicMock(), MagicMock(), MagicMock(), WSHub())
    if probing:
        disp.probing_gpu_ids.add(gpu_id)
    else:
        disp.pending_probe_gpu_ids.add(gpu_id)
    return disp


def _get_with_dispatcher(gpus: list[Gpu], dispatcher: TranscodeDispatcher) -> dict[str, dict]:
    app, token = _app(gpus)
    set_active_dispatcher(dispatcher)
    try:
        with TestClient(app) as c:
            r = c.get("/api/encoders", headers=_auth(token))
    finally:
        set_active_dispatcher(None)
    assert r.status_code == 200, r.text
    return {e["id"]: e for e in r.json()}


@pytest.mark.parametrize("probing", [False, True], ids=["pending", "probing"])
def test_gpu_kind_available_while_a_matching_device_awaits_its_first_probe(probing: bool) -> None:
    """Matches the apply gate: a pinned encoder whose only matching device is
    never-probed with its probe reserved or running is accepted there (the
    task queues), so the picker offers it too."""
    by_id = _get_with_dispatcher(
        [_gpu(vendor=GpuVendor.QSV, probed_at=None, encoder_kinds=[])],
        _awaiting_dispatcher("gpu_1", probing=probing),
    )

    qsv = by_id["qsv_h265"]
    assert qsv["available"] is True
    assert qsv["reason"] == "waiting for the first GPU probe"
    assert by_id["nvenc_h265"]["available"] is False


def test_gpu_kind_unavailable_for_an_unprobed_device_nobody_is_probing() -> None:
    by_id = _get_with_dispatcher(
        [_gpu(vendor=GpuVendor.QSV, probed_at=None, encoder_kinds=[])],
        _awaiting_dispatcher("gpu_other", probing=True),
    )
    assert by_id["qsv_h265"]["available"] is False
    assert by_id["qsv_h265"]["reason"] == "no enabled device has verified qsv_h265"


def test_gpu_kind_ignores_a_disabled_device_awaiting_its_probe() -> None:
    by_id = _get_with_dispatcher(
        [_gpu(vendor=GpuVendor.QSV, probed_at=None, encoder_kinds=[], enabled=False)],
        _awaiting_dispatcher("gpu_1", probing=True),
    )
    assert by_id["qsv_h265"]["available"] is False
