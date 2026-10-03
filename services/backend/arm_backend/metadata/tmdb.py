import asyncio
import logging
from typing import Any, Literal

import httpx

from arm_backend.config import settings
from arm_backend.metadata.base import LookupError, LookupTimeout, MetadataResult

logger = logging.getLogger("arm_backend.metadata.tmdb")


def _base_url() -> str:
    return settings.ARM_TMDB_BASE_URL


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
            r = await self._http.get(f"{_base_url()}/search/{endpoint}", params=params, headers=self._headers)
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

        # A 200 with a non-JSON body must surface as the module LookupError (which
        # the search router catches → degraded-200), not an uncaught ValueError → 500.
        # Mirrors the json-guard in find_by_imdb_id / get_external_ids.
        try:
            body = r.json()
        except ValueError as e:
            raise LookupError(f"tmdb {endpoint} returned non-JSON response") from e
        results: list[dict[str, Any]] = (body.get("results") if isinstance(body, dict) else None) or []
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
        # Enrich each candidate with its imdb/tvdb ids concurrently. A result
        # without an id can't be enriched and degrades to None ids.
        # gather(return_exceptions=True) keeps one failure from failing the batch.
        enrichable = [r for r in out if r.payload.get("id") is not None]
        maps = await asyncio.gather(
            *(self.get_external_id_map(r.payload["id"], kind) for r in enrichable),
            return_exceptions=True,
        )
        resolved = {id(r): (m if isinstance(m, dict) else {}) for r, m in zip(enrichable, maps)}
        for r in out:
            found = resolved.get(id(r), {})
            r.payload["imdb_id"] = found.get("imdb_id")
            r.payload["tvdb_id"] = found.get("tvdb_id")
        return out

    async def get_external_id_map(self, tmdb_id: int | str, kind: Literal["movie", "tv"]) -> dict[str, str]:
        """A result's IMDb and TVDB ids via TMDb `external_ids`, as
        `{"imdb_id": ..., "tvdb_id": ...}` with only the known ones present.
        Empty on any failure; NEVER raises (it runs per candidate in the search
        fan-out and per identify hit, and one failure must fail neither)."""
        try:
            r = await self._http.get(f"{_base_url()}/{kind}/{tmdb_id}/external_ids", headers=self._headers)
        except httpx.HTTPError:
            return {}
        if r.status_code != 200:
            return {}
        try:
            body = r.json()
        except ValueError:
            return {}
        if not isinstance(body, dict):
            return {}
        out: dict[str, str] = {}
        imdb = body.get("imdb_id")
        if isinstance(imdb, str) and imdb:
            out["imdb_id"] = imdb
        tvdb = body.get("tvdb_id")
        if isinstance(tvdb, int) or (isinstance(tvdb, str) and tvdb):
            out["tvdb_id"] = str(tvdb)
        return out

    async def get_external_ids(self, tmdb_id: int | str, kind: Literal["movie", "tv"]) -> str | None:
        """The result's IMDb id only (kept for callers that need just that)."""
        return (await self.get_external_id_map(tmdb_id, kind)).get("imdb_id")

    async def find_by_imdb_id(self, imdb_id: str) -> MetadataResult:
        """Resolve an imdb_id to a TMDB record via /find. Used by the
        provider-driven detail lookup when metadata_provider == 'tmdb'."""
        try:
            r = await self._http.get(
                f"{_base_url()}/find/{imdb_id}",
                params={"external_source": "imdb_id"},
                headers=self._headers,
            )
        except httpx.TimeoutException as e:
            raise LookupTimeout("tmdb find timeout") from e
        except httpx.HTTPError as e:
            raise LookupError(f"tmdb find transport error: {e}") from e
        if r.status_code == 401:
            raise LookupError("tmdb auth failed")
        if r.status_code != 200:
            raise LookupError(f"tmdb find status={r.status_code}")
        try:
            data = r.json()
        except ValueError as e:
            raise LookupError("tmdb find returned non-JSON response") from e
        if data.get("movie_results"):
            parsed = self._parse_one(data["movie_results"][0], "movie")
            if parsed is None:
                raise LookupError("tmdb find result missing title")
            return parsed
        if data.get("tv_results"):
            parsed = self._parse_one(data["tv_results"][0], "tv")
            if parsed is None:
                raise LookupError("tmdb find result missing title")
            return parsed
        raise LookupError(f"tmdb find no results for {imdb_id}")

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
