import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

import httpx
import pytest

from arm_common import DiscType, JobStatus
from arm_common.schemas import HeldJobView, JobView
from arm_ripper.backend_client import BackendClient


def _client(handler) -> BackendClient:
    c = BackendClient("https://backend", "tok", hostname="h", drive_id="drv_test")
    c._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://backend")
    return c


def _job_view() -> JobView:
    return JobView(
        id="job_1",
        drive_id="drv_1",
        disc_type=DiscType.DVD,
        status=JobStatus.RIPPING,
        title="Iron Man",
        year=2008,
        metadata_json={},
        resumed_from_crash=False,
    )


def _held_view() -> HeldJobView:
    return HeldJobView(job=_job_view(), paused=True)


# (method name, URL suffix, served model)
_LOOKUPS = [
    pytest.param("get_in_flight_job", "in-flight-job", _job_view, id="in-flight"),
    pytest.param("get_current_job", "current-job", _job_view, id="current"),
    pytest.param("get_held_job", "held-job", _held_view, id="held"),
]


@pytest.mark.parametrize(("method", "suffix", "make"), _LOOKUPS)
async def test_lookup_returns_the_parsed_model_from_a_get(method, suffix, make) -> None:
    served = make()
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json=served.model_dump(mode="json"))

    result = await getattr(_client(handler), method)("drv_1")
    assert result == served
    assert type(result) is type(served)
    assert seen == {"method": "GET", "path": f"/api/ripper/drives/drv_1/{suffix}"}


@pytest.mark.parametrize(("method", "suffix", "make"), _LOOKUPS)
async def test_lookup_returns_none_on_404(method, suffix, make) -> None:
    assert await getattr(_client(lambda req: httpx.Response(404)), method)("drv_1") is None


@pytest.mark.parametrize(("method", "suffix", "make"), _LOOKUPS)
async def test_lookup_raises_on_server_error(method, suffix, make) -> None:
    with pytest.raises(httpx.HTTPStatusError):
        await getattr(_client(lambda req: httpx.Response(500)), method)("drv_1")


async def test_get_or_none_parses_the_body_into_the_given_model() -> None:
    served = _job_view()
    c = _client(lambda req: httpx.Response(200, json=served.model_dump(mode="json")))
    result = await c._get_or_none("/some/path", JobView)
    assert result == served
    assert type(result) is JobView


async def test_get_or_none_returns_none_on_404() -> None:
    assert await _client(lambda req: httpx.Response(404))._get_or_none("/some/path", JobView) is None


async def test_get_or_none_raises_on_server_error() -> None:
    with pytest.raises(httpx.HTTPStatusError):
        await _client(lambda req: httpx.Response(500))._get_or_none("/some/path", JobView)


async def test_get_or_none_gets_exactly_the_given_path() -> None:
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(404)

    await _client(handler)._get_or_none("/api/x/y", JobView)
    assert seen == {"method": "GET", "path": "/api/x/y"}
