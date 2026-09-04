import asyncio
import logging
import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

import httpx
import pytest

from arm_ripper import main as ripper_main
from arm_ripper.backend_client import RegisterRefused


class _Client:
    def __init__(self, answers):
        self._answers = list(answers)
        self.calls = 0

    async def register(self, **kw):
        self.calls += 1
        answer = self._answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class _Drive:
    id = "drv_test"


async def test_register_retries_transport_errors_then_returns_the_id(monkeypatch) -> None:
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(ripper_main.asyncio, "sleep", fake_sleep)
    client = _Client([httpx.ConnectError("down"), _Drive()])
    assert await ripper_main.register_with_retry(client, "/dev/sr0") == "drv_test"
    assert client.calls == 2 and sleeps == [1.0]


async def test_register_refused_parks_forever(monkeypatch, caplog) -> None:
    parked = asyncio.Event()

    class _NeverEvent:
        async def wait(self):
            parked.set()
            raise asyncio.CancelledError  # stand-in for "blocks forever"

    monkeypatch.setattr(ripper_main.asyncio, "Event", _NeverEvent)
    client = _Client([RegisterRefused("identity mismatch: row is bound to A but the ripper resolved B")])
    with caplog.at_level(logging.ERROR, logger="arm_ripper"):
        with pytest.raises(asyncio.CancelledError):
            await ripper_main.register_with_retry(client, "/dev/sr0")
    assert parked.is_set() and client.calls == 1
    assert "identity mismatch" in caplog.text and "left running for diagnosis" in caplog.text
