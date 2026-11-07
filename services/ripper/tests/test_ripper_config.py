"""Unit tests for the fail-open ripper-config lookup."""

import logging

import httpx

from arm_common.schemas import RipperConfigView
from arm_ripper.ripper_config import ripper_config_or_none


class _Client:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    async def get_ripper_config(self):
        if self._error is not None:
            raise self._error
        return self._result


async def test_returns_the_clients_config_on_success():
    """Pin that a successful lookup returns the client's config untouched."""
    cfg = RipperConfigView(
        auto_rip_on_insert=True,
        makemkv_key=None,
        community_keydb_enabled=True,
        ripping_paused=False,
        manual_wait_seconds=30,
        makemkv_sdf_enabled=True,
    )
    assert await ripper_config_or_none(_Client(result=cfg), "what", "fallback") is cfg


async def test_http_error_returns_none_and_logs_one_warning(caplog):
    """Pin that an HTTPError yields None and exactly one WARNING on the job controller logger."""
    error = httpx.ConnectError("boom")
    with caplog.at_level(logging.WARNING, logger="arm_ripper.job_controller"):
        result = await ripper_config_or_none(_Client(error=error), "lookup", "doing the fallback")
    assert result is None
    assert [(r.name, r.levelno, r.getMessage()) for r in caplog.records] == [
        ("arm_ripper.job_controller", logging.WARNING, "lookup failed (boom); doing the fallback")
    ]
