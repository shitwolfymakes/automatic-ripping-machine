import logging
from typing import Any
from urllib.parse import quote

import httpx

from arm_backend.config import settings
from arm_backend.metadata.base import LookupError, LookupTimeout, MetadataResult

logger = logging.getLogger("arm_backend.metadata.tvdb")


def _base_url() -> str:
    return settings.ARM_TVDB_BASE_URL


def series_to_result(entry: Any) -> MetadataResult | None:
    """One TVDB search entry (or the `series` object of a remoteid result)
    → MetadataResult, or None without a name."""
    if not isinstance(entry, dict):
        return None
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        return None
    raw_year = entry.get("year")
    year = int(str(raw_year)[:4]) if raw_year is not None and str(raw_year)[:4].isdigit() else None
    payload: dict[str, Any] = dict(entry)
    tvdb_id = entry.get("tvdb_id") or entry.get("id")
    if tvdb_id is not None and str(tvdb_id):
        payload["tvdb_id"] = str(tvdb_id)
    for remote in entry.get("remote_ids") or []:
        if isinstance(remote, dict) and str(remote.get("sourceName", "")).upper() == "IMDB" and remote.get("id"):
            payload["imdb_id"] = str(remote["id"])
            break
    poster = entry.get("image_url") or entry.get("image")
    if isinstance(poster, str) and poster.startswith("http"):
        payload["poster_url"] = poster
    return MetadataResult(title=name, year=year, kind="tv", payload=payload)


class TVDBClient:
    """TVDB v4 client. Key validation plus TV title search (PR 2b);
    episode listing lives in identity/episodes/providers/tvdb.py.

    TVDB v4 authenticates via a login handshake: POST /v4/login with the
    API key returns a bearer token.
    """

    def __init__(self, api_key: str, http: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._http = http

    _token: str | None = None

    async def _login(self) -> str:
        try:
            r = await self._http.post(f"{_base_url()}/login", json={"apikey": self._api_key})
        except httpx.TimeoutException as e:
            raise LookupTimeout("tvdb login timeout") from e
        except httpx.HTTPError as e:
            raise LookupError(f"tvdb login transport error: {e}") from e
        if r.status_code == 401:
            logger.warning("tvdb auth_failed status=401")
            raise LookupError("tvdb auth failed")
        if r.status_code >= 500:
            raise LookupError(f"tvdb login 5xx status={r.status_code}")
        if r.status_code != 200:
            raise LookupError(f"tvdb login status={r.status_code}")
        try:
            token = r.json()["data"]["token"]
        except (ValueError, KeyError, TypeError) as e:
            raise LookupError("tvdb login malformed response") from e
        if not isinstance(token, str) or not token:
            raise LookupError("tvdb login returned no token")
        self._token = token
        return token

    async def _get_authed(self, path: str, params: dict[str, Any] | None = None) -> Any:
        token = self._token or await self._login()
        for attempt in (1, 2):
            try:
                r = await self._http.get(
                    f"{_base_url()}{path}", params=params, headers={"Authorization": f"Bearer {token}"}
                )
            except httpx.TimeoutException as e:
                raise LookupTimeout("tvdb timeout") from e
            except httpx.HTTPError as e:
                raise LookupError(f"tvdb transport error: {e}") from e
            if r.status_code == 401 and attempt == 1:
                token = await self._login()  # expired token: one re-login
                continue
            if r.status_code == 401:
                raise LookupError("tvdb auth failed after re-login")
            if r.status_code == 404:
                raise LookupError("tvdb miss")
            if r.status_code != 200:
                raise LookupError(f"tvdb status={r.status_code}")
            try:
                return r.json()
            except ValueError as e:
                raise LookupError("tvdb malformed response") from e

    async def search_candidates(self, title: str, limit: int = 10) -> list[MetadataResult]:
        body = await self._get_authed("/search", {"query": title, "type": "series"})
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            raise LookupError("tvdb malformed response")
        out: list[MetadataResult] = []
        for entry in data:
            result = series_to_result(entry)
            if result is not None:
                out.append(result)
            if len(out) >= limit:
                break
        return out

    async def search_series(self, title: str) -> MetadataResult:
        results = await self.search_candidates(title, limit=1)
        if not results:
            raise LookupError("tvdb search no results")
        return results[0]

    async def lookup_by_imdb_id(self, imdb_id: str) -> MetadataResult:
        body = await self._get_authed(f"/search/remoteid/{quote(imdb_id, safe='')}")
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            raise LookupError("tvdb malformed response")
        for entry in data:
            series = entry.get("series") if isinstance(entry, dict) else None
            result = series_to_result(series)
            if result is not None:
                result.payload.setdefault("imdb_id", imdb_id)
                return result
        raise LookupError("tvdb remoteid miss")

    async def validate_key(self) -> None:
        """POST /v4/login. Returns None on success; raises LookupError on
        auth/transport failure, LookupTimeout on timeout."""
        await self._login()
