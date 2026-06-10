"""TVDB v4 client: login/validate_key only (Tier-1 scope)."""

import httpx
import pytest
import respx

from arm_backend.metadata.base import LookupError, LookupTimeout
from arm_backend.metadata.tvdb import TVDBClient

_LOGIN_URL = "https://api4.thetvdb.com/v4/login"


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


@respx.mock
async def test_validate_key_success(http_client):
    respx.post(_LOGIN_URL).mock(
        return_value=httpx.Response(200, json={"status": "success", "data": {"token": "jwt-abc"}})
    )
    client = TVDBClient("good-key", http_client)
    await client.validate_key()  # returns None, no raise
    sent = respx.calls.last.request
    assert b"good-key" in sent.content


@respx.mock
async def test_validate_key_invalid_raises_lookuperror(http_client):
    respx.post(_LOGIN_URL).mock(return_value=httpx.Response(401, json={"status": "failure"}))
    client = TVDBClient("bad-key", http_client)
    with pytest.raises(LookupError):
        await client.validate_key()


@respx.mock
async def test_validate_key_5xx_raises_lookuperror(http_client):
    respx.post(_LOGIN_URL).mock(return_value=httpx.Response(503))
    client = TVDBClient("k", http_client)
    with pytest.raises(LookupError):
        await client.validate_key()


@respx.mock
async def test_validate_key_timeout_raises_lookuptimeout(http_client):
    respx.post(_LOGIN_URL).mock(side_effect=httpx.TimeoutException("slow"))
    client = TVDBClient("k", http_client)
    with pytest.raises(LookupTimeout):
        await client.validate_key()
