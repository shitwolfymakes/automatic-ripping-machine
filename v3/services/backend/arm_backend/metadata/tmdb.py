import logging
from typing import Any, Literal

import httpx

from arm_backend.metadata.base import LookupError, LookupTimeout, MetadataResult

logger = logging.getLogger("arm_backend.metadata.tmdb")

_BASE_URL = "https://api.themoviedb.org/3"


class TMDBClient:
    """TMDB v3 search via v4 bearer auth.

    The v4 bearer token authorizes v3 read endpoints, which keeps the API key
    out of query strings (and httpx DEBUG request logs).
    """

    def __init__(self, api_key: str, http: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._http = http

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"}

    async def search_movie(self, title: str, year: int | None = None) -> MetadataResult:
        params: dict[str, Any] = {"query": title}
        if year is not None:
            params["year"] = year
        return await self._search("movie", params, kind="movie")

    async def search_tv(self, title: str) -> MetadataResult:
        return await self._search("tv", {"query": title}, kind="tv")

    async def _search(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        kind: Literal["movie", "tv"],
    ) -> MetadataResult:
        try:
            r = await self._http.get(
                f"{_BASE_URL}/search/{endpoint}",
                params=params,
                headers=self._headers,
            )
        except httpx.TimeoutException as e:
            raise LookupTimeout(f"tmdb {endpoint} timeout") from e
        except httpx.HTTPError as e:
            raise LookupError(f"tmdb {endpoint} transport error: {e}") from e

        if r.status_code == 401:
            logger.warning("tmdb auth_failed status=401")
            raise LookupError("tmdb auth failed")
        if r.status_code >= 500:
            raise LookupError(f"tmdb {endpoint} 5xx status={r.status_code}")
        if r.status_code != 200:
            raise LookupError(f"tmdb {endpoint} status={r.status_code}")

        body = r.json()
        results = body.get("results") or []
        if not results:
            raise LookupError(f"tmdb {endpoint} no results")

        top = results[0]
        if endpoint == "movie":
            release = top.get("release_date") or ""
            year_val = int(release[:4]) if release[:4].isdigit() else None
            title_val = top.get("title") or top.get("original_title") or ""
        else:
            release = top.get("first_air_date") or ""
            year_val = int(release[:4]) if release[:4].isdigit() else None
            title_val = top.get("name") or top.get("original_name") or ""

        if not title_val:
            raise LookupError(f"tmdb {endpoint} top result missing title")

        return MetadataResult(title=title_val, year=year_val, kind=kind, payload=top)
