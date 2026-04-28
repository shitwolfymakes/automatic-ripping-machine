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

    async def lookup_by_title(
        self,
        title: str,
        year: int | None = None,
        kind: Literal["movie", "tv"] = "movie",
    ) -> MetadataResult:
        params: dict[str, Any] = {"apikey": self._api_key, "t": title, "type": kind}
        if year is not None:
            params["y"] = year

        try:
            r = await self._http.get(_BASE_URL, params=params)
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

        body = r.json()
        if body.get("Response") != "True":
            raise LookupError(f"omdb miss: {body.get('Error', 'unknown')}")

        title_val = body.get("Title")
        year_str = body.get("Year") or ""
        year_val = int(year_str[:4]) if year_str[:4].isdigit() else None
        if not title_val:
            raise LookupError("omdb hit missing title")

        return MetadataResult(title=title_val, year=year_val, kind=kind, payload=body)
