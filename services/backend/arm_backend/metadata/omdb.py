import logging
from typing import Any, Literal

import httpx

from arm_backend.metadata.base import LookupError, LookupTimeout, MetadataResult

logger = logging.getLogger("arm_backend.metadata.omdb")

_BASE_URL = "https://www.omdbapi.com/"


class OMDBClient:
    """OMDB title search. Movie-only fallback for the v3.0 dispatcher.

    OMDB requires the api key as a query parameter. This is a public service
    with no bearer-token alternative, so we accept the leak risk and rely on
    log scrubbing (the URL never lands in metadata_json).
    """

    def __init__(self, api_key: str, http: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._http = http

    async def _get_json(self, params: dict[str, Any]) -> dict[str, Any]:
        """GET the OMDB endpoint and return the parsed JSON body.

        Centralizes the transport + HTTP-status handling shared by every OMDB
        call: TimeoutException -> LookupTimeout, other transport errors and
        401/5xx/non-200 -> LookupError. `apikey` is injected here so callers
        only pass the query-specific params.
        """
        try:
            r = await self._http.get(_BASE_URL, params={"apikey": self._api_key, **params})
        except httpx.TimeoutException as e:
            raise LookupTimeout("omdb timeout") from e
        except httpx.HTTPError as e:
            raise LookupError(f"omdb transport error: {e}") from e

        if r.status_code == 401:
            logger.warning("omdb auth_failed status=401")
            raise LookupError("omdb auth failed")
        if r.status_code >= 500:
            raise LookupError(f"omdb 5xx status={r.status_code}")
        if r.status_code != 200:
            raise LookupError(f"omdb status={r.status_code}")

        body: dict[str, Any] = r.json()
        return body

    async def lookup_by_title(
        self,
        title: str,
        year: int | None = None,
        kind: Literal["movie", "tv"] = "movie",
    ) -> MetadataResult:
        params: dict[str, Any] = {"t": title, "type": kind}
        if year is not None:
            params["y"] = year

        body = await self._get_json(params)
        if body.get("Response") != "True":
            raise LookupError(f"omdb miss: {body.get('Error', 'unknown')}")

        title_val = body.get("Title")
        year_str = body.get("Year") or ""
        year_val = int(year_str[:4]) if year_str[:4].isdigit() else None
        if not title_val:
            raise LookupError("omdb hit missing title")

        return MetadataResult(title=title_val, year=year_val, kind=kind, payload=body)

    async def search_candidates(
        self,
        title: str,
        kind: Literal["movie", "tv"] = "movie",
        limit: int = 10,
    ) -> list[MetadataResult]:
        """Return up to `limit` candidates for an interactive search (OMDB `s=`)."""
        body = await self._get_json({"s": title, "type": kind})
        if body.get("Response") != "True":
            return []  # "Movie not found!" etc. — a real empty result, not an error
        out: list[MetadataResult] = []
        for item in (body.get("Search") or [])[:limit]:
            title_val = item.get("Title")
            if not title_val:
                continue
            year_str = item.get("Year") or ""
            year_val = int(year_str[:4]) if year_str[:4].isdigit() else None
            out.append(MetadataResult(title=title_val, year=year_val, kind=kind, payload=item))
        return out

    async def lookup_by_imdb_id(self, imdb_id: str) -> MetadataResult:
        """Full details for a known IMDb id (OMDB `i=`)."""
        body = await self._get_json({"i": imdb_id})
        if body.get("Response") != "True":
            raise LookupError(f"omdb miss: {body.get('Error', 'unknown')}")
        title_val = body.get("Title")
        if not title_val:
            raise LookupError("omdb hit missing title")
        year_str = body.get("Year") or ""
        year_val = int(year_str[:4]) if year_str[:4].isdigit() else None
        kind: Literal["movie", "tv"] = "tv" if body.get("Type") == "series" else "movie"
        return MetadataResult(title=title_val, year=year_val, kind=kind, payload=body)
