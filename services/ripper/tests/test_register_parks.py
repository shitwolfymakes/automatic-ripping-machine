import logging
import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

import httpx

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


async def test_register_refused_retries_slowly_and_logs_once(monkeypatch, caplog) -> None:
    """E1: a register refusal is self-healing, not fatal — retry slowly
    (REGISTER_REFUSED_RETRY_SECONDS) instead of parking forever. An
    unchanged refusal is logged once at ERROR (repeats downgrade to DEBUG,
    so a stuck enrollment doesn't spam the log every minute)."""
    sleeps: list[float] = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(ripper_main.asyncio, "sleep", fake_sleep)
    same_refusal = RegisterRefused("identity mismatch: A/B")
    client = _Client([same_refusal, RegisterRefused("identity mismatch: A/B"), _Drive()])
    with caplog.at_level(logging.DEBUG, logger="arm_ripper"):
        drive_id = await ripper_main.register_with_retry(client, "/dev/sr0")
    assert drive_id == "drv_test"
    assert client.calls == 3
    assert sleeps == [ripper_main.REGISTER_REFUSED_RETRY_SECONDS, ripper_main.REGISTER_REFUSED_RETRY_SECONDS]
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR and "identity mismatch" in r.getMessage()]
    assert len(error_records) == 1
    assert "left running for diagnosis" in error_records[0].getMessage()
