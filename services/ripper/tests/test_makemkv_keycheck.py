import asyncio

import httpx
import pytest
import respx

from arm_common import MakemkvKeyState
from arm_ripper.backend_client import BackendClient
from arm_ripper.main import makemkv_key_changed
from arm_ripper.scan import makemkv as mk


class _FakeProc:
    def __init__(self, lines: list[bytes], returncode: int = 0):
        self._lines = lines
        self.returncode = returncode
        self.stdout = self._aiter(lines)
        self.stderr = self._aiter([])

    @staticmethod
    def _aiter(items):
        async def gen():
            for it in items:
                yield it

        return gen()

    def kill(self):
        self.returncode = -9

    async def wait(self):
        return self.returncode


@pytest.fixture
def fake_exec(monkeypatch):
    holder = {}

    async def _exec(*cmd, **kw):
        return holder["proc"]

    monkeypatch.setattr(mk.asyncio, "create_subprocess_exec", _exec)
    return holder


async def test_probe_format_invalid_skips_subprocess():
    state, detail = await mk.probe_makemkv_key("not-a-serial")
    assert state == MakemkvKeyState.FORMAT_INVALID
    assert detail


async def test_probe_clean_is_valid(fake_exec):
    fake_exec["proc"] = _FakeProc([b'MSG:1005,0,1,"MakeMKV started"\n', b'DRV:0,256,999,0,"","",""\n'], returncode=0)
    state, _ = await mk.probe_makemkv_key("M-validkey")
    assert state == MakemkvKeyState.VALID


async def test_probe_5021_is_binary_expired(fake_exec):
    fake_exec["proc"] = _FakeProc([b'MSG:5021,131332,1,"too old"\n'], returncode=253)
    state, _ = await mk.probe_makemkv_key("M-validkey")
    assert state == MakemkvKeyState.BINARY_EXPIRED


@pytest.mark.parametrize("code", [b"MSG:5052,", b"MSG:5055,"])
async def test_probe_5052_5055_is_unregistered(fake_exec, code):
    fake_exec["proc"] = _FakeProc([code + b'0,1,"eval expired"\n'], returncode=0)
    state, _ = await mk.probe_makemkv_key("M-validkey")
    assert state == MakemkvKeyState.UNREGISTERED_OR_EXPIRED


async def test_probe_binary_missing_is_probe_failed(monkeypatch):
    async def _raise(*a, **k):
        raise FileNotFoundError("makemkvcon")

    monkeypatch.setattr(mk.asyncio, "create_subprocess_exec", _raise)
    state, detail = await mk.probe_makemkv_key("M-validkey")
    assert state == MakemkvKeyState.PROBE_FAILED
    assert "makemkvcon" in (detail or "")


async def test_probe_never_raises_on_timeout(fake_exec, monkeypatch):
    fake_exec["proc"] = _FakeProc([], returncode=0)

    async def _timeout(*a, **k):
        raise asyncio.TimeoutError

    monkeypatch.setattr(mk.asyncio, "wait_for", _timeout)
    state, _ = await mk.probe_makemkv_key("M-validkey")
    assert state == MakemkvKeyState.PROBE_FAILED


@respx.mock
async def test_report_makemkv_key_status_posts_body():
    route = respx.post("https://bk/api/ripper/makemkv-key-status").mock(return_value=httpx.Response(204))
    client = BackendClient("https://bk", "tok", "host1")
    await client.report_makemkv_key_status(state=MakemkvKeyState.VALID, detail="ok")
    await client.close()
    assert route.called
    sent = route.calls.last.request
    assert b'"state":"valid"' in sent.content


def test_makemkv_key_changed_detects_transitions():
    assert makemkv_key_changed(prev=None, current="M-a") is True
    assert makemkv_key_changed(prev="M-a", current="M-a") is False
    assert makemkv_key_changed(prev="M-a", current="M-b") is True
    assert makemkv_key_changed(prev="M-a", current=None) is True
    assert makemkv_key_changed(prev=None, current=None) is False
