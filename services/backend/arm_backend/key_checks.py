"""Whether a provider accepts an API key, or what the ripper last said about the MakeMKV key."""

from collections.abc import Awaitable, Callable
from typing import Literal

import httpx

from arm_backend.config import settings
from arm_backend.makemkv_status import makemkv_state_detail
from arm_common import Config
from arm_common.schemas import KeyCheckResponse

_KEY_CHECK_TIMEOUT_SECONDS = 10.0

KeyCheckOutcome = tuple[Literal["ok", "invalid", "error"], str | None]


async def _check_tmdb(http: httpx.AsyncClient, key: str) -> KeyCheckOutcome:
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    try:
        r = await http.get(
            f"{settings.ARM_TMDB_BASE_URL}/configuration", headers=headers, timeout=_KEY_CHECK_TIMEOUT_SECONDS
        )
    except httpx.HTTPError as exc:
        return "error", str(exc)
    if r.status_code == 200:
        return "ok", None
    if r.status_code == 401:
        return "invalid", "TMDb rejected the key"
    return "error", f"tmdb status={r.status_code}"


async def _check_omdb(http: httpx.AsyncClient, key: str) -> KeyCheckOutcome:
    try:
        r = await http.get(
            settings.ARM_OMDB_BASE_URL,
            params={"apikey": key, "i": "tt0111161"},
            timeout=_KEY_CHECK_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        return "error", str(exc)
    if r.status_code == 401:
        return "invalid", "OMDb rejected the key"
    if r.status_code != 200:
        return "error", f"omdb status={r.status_code}"
    try:
        body = r.json()
    except ValueError as exc:
        return "error", f"omdb returned a non-JSON response: {exc}"
    if body.get("Response") == "True":
        return "ok", None
    if body.get("Response") == "False":
        return "invalid", body.get("Error", "omdb rejected the key")
    return "error", "omdb returned an unexpected response"


async def _check_tvdb(http: httpx.AsyncClient, key: str) -> KeyCheckOutcome:
    try:
        r = await http.post(
            f"{settings.ARM_TVDB_BASE_URL}/login",
            json={"apikey": key},
            timeout=_KEY_CHECK_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        return "error", str(exc)
    if r.status_code == 200:
        return "ok", None
    if r.status_code == 401:
        return "invalid", "TVDB rejected the key"
    return "error", f"tvdb status={r.status_code}"


def makemkv_key_status(cfg: Config, stored_key: str, unsaved_value: str | None) -> KeyCheckResponse:
    if unsaved_value is not None and unsaved_value != stored_key:
        return KeyCheckResponse(
            name="makemkv",
            status="unknown",
            detail="save the key; the ripper verifies it before the next rip",
            checked_at=None,
        )
    # The ripper's verdict wins: with no purchased key stored it fetches the
    # monthly beta key itself, so "valid" is real even when Config holds
    # nothing. "no key set" only applies when there is no verdict either.
    if cfg.makemkv_key_valid is True:
        detail = None if stored_key else "using the monthly beta key"
        return KeyCheckResponse(name="makemkv", status="ok", detail=detail, checked_at=cfg.makemkv_key_checked_at)
    if cfg.makemkv_key_valid is False:
        return KeyCheckResponse(
            name="makemkv",
            status="invalid",
            detail=makemkv_state_detail(cfg.makemkv_key_state),
            checked_at=cfg.makemkv_key_checked_at,
        )
    if not stored_key and cfg.makemkv_key_checked_at is None:
        return KeyCheckResponse(
            name="makemkv",
            status="missing",
            detail="no key set; the ripper fetches the monthly beta key when it starts",
            checked_at=None,
        )
    detail = "probe failed" if cfg.makemkv_key_state == "probe_failed" else "not checked yet"
    return KeyCheckResponse(name="makemkv", status="unknown", detail=detail, checked_at=cfg.makemkv_key_checked_at)


# check_key only passes "tmdb", "omdb" or "tvdb" here (the Literal validates name; "makemkv" returns earlier).
_ONLINE_KEY_CHECKS: dict[str, Callable[[httpx.AsyncClient, str], Awaitable[KeyCheckOutcome]]] = {
    "tmdb": _check_tmdb,
    "omdb": _check_omdb,
    "tvdb": _check_tvdb,
}


async def check_online_key(http: httpx.AsyncClient, name: str, key: str) -> KeyCheckOutcome:
    return await _ONLINE_KEY_CHECKS[name](http, key)
