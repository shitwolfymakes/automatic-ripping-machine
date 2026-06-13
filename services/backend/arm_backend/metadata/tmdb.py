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

    async def _get_results(self, endpoint: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """GET /search/{endpoint} and return the raw `results` list.

        Centralizes the transport + HTTP-status handling shared by the top-hit
        and multi-candidate search paths: TimeoutException -> LookupTimeout,
        other transport errors and 401/5xx/non-200 -> LookupError.
        """
        try:
            r = await self._http.get(f"{_BASE_URL}/search/{endpoint}", params=params, headers=self._headers)
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

        results: list[dict[str, Any]] = r.json().get("results") or []
        return results

    @staticmethod
    def _parse_one(top: dict[str, Any], kind: Literal["movie", "tv"]) -> MetadataResult | None:
        """Map one TMDB result dict to a MetadataResult, or None if it has no
        usable title. Movie/TV differ only in the title/date field names."""
        if kind == "movie":
            release = top.get("release_date") or ""
            title_val = top.get("title") or top.get("original_title") or ""
        else:
            release = top.get("first_air_date") or ""
            title_val = top.get("name") or top.get("original_name") or ""
        if not title_val:
            return None
        year_val = int(release[:4]) if release[:4].isdigit() else None
        return MetadataResult(title=title_val, year=year_val, kind=kind, payload=top)

    async def search_movie(self, title: str, year: int | None = None) -> MetadataResult:
        params: dict[str, Any] = {"query": title}
        if year is not None:
            params["year"] = year
        return await self._search("movie", params, kind="movie")

    async def search_tv(self, title: str) -> MetadataResult:
        return await self._search("tv", {"query": title}, kind="tv")

    async def search_movie_candidates(
        self, title: str, year: int | None = None, limit: int = 10
    ) -> list[MetadataResult]:
        params: dict[str, Any] = {"query": title}
        if year is not None:
            params["year"] = year
        return await self._search_candidates("movie", params, kind="movie", limit=limit)

    async def search_tv_candidates(self, title: str, limit: int = 10) -> list[MetadataResult]:
        return await self._search_candidates("tv", {"query": title}, kind="tv", limit=limit)

    async def _search_candidates(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        kind: Literal["movie", "tv"],
        limit: int,
    ) -> list[MetadataResult]:
        results = await self._get_results(endpoint, params)
        out: list[MetadataResult] = []
        for top in results[:limit]:
            parsed = self._parse_one(top, kind)
            if parsed is not None:
                out.append(parsed)
        return out

    async def _search(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        kind: Literal["movie", "tv"],
    ) -> MetadataResult:
        results = await self._get_results(endpoint, params)
        if not results:
            raise LookupError(f"tmdb {endpoint} no results")
        parsed = self._parse_one(results[0], kind)
        if parsed is None:
            raise LookupError(f"tmdb {endpoint} top result missing title")
        return parsed
