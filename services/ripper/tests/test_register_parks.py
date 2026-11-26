import logging
import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

import httpx

from arm_ripper import registration
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

    monkeypatch.setattr(registration.asyncio, "sleep", fake_sleep)
    client = _Client([httpx.ConnectError("down"), _Drive()])
    assert await registration.register_with_retry(client, "/dev/sr0") == "drv_test"
    assert client.calls == 2 and sleeps == [1.0]


async def test_register_refused_retries_slowly_and_logs_once(monkeypatch, caplog) -> None:
    """A register refusal is self-healing, not fatal — retry slowly
    (REGISTER_REFUSED_RETRY_SECONDS) instead of parking forever. An
    unchanged refusal is logged once at ERROR (repeats downgrade to DEBUG,
    so a stuck enrollment doesn't spam the log every minute)."""
    sleeps: list[float] = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(registration.asyncio, "sleep", fake_sleep)
    same_refusal = RegisterRefused("identity mismatch: A/B")
    client = _Client([same_refusal, RegisterRefused("identity mismatch: A/B"), _Drive()])
    with caplog.at_level(logging.DEBUG, logger="arm_ripper"):
        drive_id = await registration.register_with_retry(client, "/dev/sr0")
    assert drive_id == "drv_test"
    assert client.calls == 3
    assert sleeps == [registration.REGISTER_REFUSED_RETRY_SECONDS, registration.REGISTER_REFUSED_RETRY_SECONDS]
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR and "identity mismatch" in r.getMessage()]
    assert len(error_records) == 1
    assert "left running for diagnosis" in error_records[0].getMessage()


def _refusal_records(caplog):
    return [(r.levelno, r.getMessage()) for r in caplog.records if r.name == "arm_ripper"]


def test_log_refusal_first_refusal_logs_error_and_returns_the_text(monkeypatch, caplog) -> None:
    monkeypatch.setattr(registration.settings, "ARM_DRIVE_ID", "drv_test")
    with caplog.at_level(logging.DEBUG, logger="arm_ripper"):
        returned = registration._log_refusal(RegisterRefused("not enrolled"), None)
    assert returned == "not enrolled"
    expected = (
        "register refused for drive_id=drv_test: not enrolled — container left running for diagnosis; "
        f"fix the enrollment in the UI; retrying in {registration.REGISTER_REFUSED_RETRY_SECONDS:.0f}s"
    )
    assert _refusal_records(caplog) == [(logging.ERROR, expected)]


def test_log_refusal_unchanged_repeat_logs_debug(caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger="arm_ripper"):
        returned = registration._log_refusal(RegisterRefused("not enrolled"), "not enrolled")
    assert returned == "not enrolled"
    assert [level for level, _ in _refusal_records(caplog)] == [logging.DEBUG]


def test_log_refusal_changed_text_logs_error_again(caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger="arm_ripper"):
        returned = registration._log_refusal(RegisterRefused("identity mismatch"), "not enrolled")
    assert returned == "identity mismatch"
    assert [level for level, _ in _refusal_records(caplog)] == [logging.ERROR]
