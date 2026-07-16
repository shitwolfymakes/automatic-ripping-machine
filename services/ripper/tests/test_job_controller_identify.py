"""Unit tests for JobController._identify_with_retry error classification.

Verifies that non-retriable 4xx responses (e.g. 409 ripping-paused) are
re-raised immediately instead of retrying forever while holding _active_lock.
"""

import asyncio

import httpx
import pytest

from arm_common import DiscType
from arm_common.schemas import ScanResult
from arm_ripper.job_controller import JobController


def _req() -> httpx.Request:
    return httpx.Request("POST", "https://bk/api/ripper/identify")


def _status_error(code: int) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError(f"{code}", request=_req(), response=httpx.Response(code, request=_req()))


class _StubClient:
    def __init__(self, error: Exception):
        self._error = error
        self.calls = 0

    async def identify(self, **kw):
        self.calls += 1
        raise self._error

    # Satisfy _configured_makemkv_key path (not called in these tests, but
    # type-checker-friendly to have):
    async def get_ripper_config(self):  # pragma: no cover
        raise AssertionError("get_ripper_config should not be called in identify tests")


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Replace asyncio.sleep in job_controller with an instant no-op so retry
    loops spin immediately without burning wall-clock time.

    We import the real asyncio.sleep up-front so the patched version can call
    the original without recursive self-reference."""
    import asyncio as _asyncio

    _real_sleep = _asyncio.sleep

    async def _fast(_delay):
        # Yield once to keep the event loop cooperative, but without a real wait.
        await _real_sleep(0)

    monkeypatch.setattr("arm_ripper.job_controller.asyncio.sleep", _fast)


def _controller(client) -> JobController:
    """Build a real JobController with a stub client, mirroring existing tests."""
    jc = JobController(client, "drv_test")
    # _identify_with_retry only touches self._client, self._drive_id, and
    # asyncio.sleep — no other setup needed for these focused tests.
    return jc


_SCAN = ScanResult(disc_type=DiscType.DVD, volume_label="TEST")


@pytest.mark.asyncio
async def test_identify_409_reraises_without_retry():
    """A 409 must be re-raised on the FIRST call — no retry loop."""
    jc = _controller(_StubClient(_status_error(409)))
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await jc._identify_with_retry(_SCAN, pending_session_id=None)
    assert exc_info.value.response.status_code == 409
    assert jc._client.calls == 1  # the load-bearing assertion: zero retries


@pytest.mark.asyncio
async def test_identify_400_reraises_without_retry():
    """400 Bad Request is also a non-retriable client error."""
    jc = _controller(_StubClient(_status_error(400)))
    with pytest.raises(httpx.HTTPStatusError):
        await jc._identify_with_retry(_SCAN, pending_session_id=None)
    assert jc._client.calls == 1


@pytest.mark.asyncio
async def test_identify_422_reraises_without_retry():
    """422 Unprocessable Entity is a non-retriable client error."""
    jc = _controller(_StubClient(_status_error(422)))
    with pytest.raises(httpx.HTTPStatusError):
        await jc._identify_with_retry(_SCAN, pending_session_id=None)
    assert jc._client.calls == 1


@pytest.mark.asyncio
async def test_identify_429_retries():
    """429 Too Many Requests is rate-limiting — must be retried."""
    stub = _StubClient(_status_error(429))
    jc = _controller(stub)
    task = asyncio.ensure_future(jc._identify_with_retry(_SCAN, pending_session_id=None))
    # Yield enough times for at least 2 identify calls to happen.
    for _ in range(10):
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stub.calls >= 2  # 429 is retriable


@pytest.mark.asyncio
async def test_identify_transport_error_retries():
    """Transport errors (connect failures, etc.) must retry with backoff."""
    stub = _StubClient(httpx.ConnectError("down", request=_req()))
    jc = _controller(stub)
    task = asyncio.ensure_future(jc._identify_with_retry(_SCAN, pending_session_id=None))
    for _ in range(10):
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stub.calls >= 2  # transport error is retriable


@pytest.mark.asyncio
async def test_identify_500_retries():
    """5xx is transient — must retry."""
    stub = _StubClient(_status_error(500))
    jc = _controller(stub)
    task = asyncio.ensure_future(jc._identify_with_retry(_SCAN, pending_session_id=None))
    for _ in range(10):
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stub.calls >= 2  # 5xx is retriable
