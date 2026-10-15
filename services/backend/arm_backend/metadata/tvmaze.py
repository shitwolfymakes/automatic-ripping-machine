"""TVmaze title search (PR 2b). Keyless; TVmaze asks for at most 20
requests per 10 s, which a search box and identify stay well under.
Episode listing lives in identity/episodes/providers/tvmaze.py."""

import logging
from typing import Any

import httpx

from arm_backend.config import settings
from arm_backend.metadata.base import LookupError, LookupTimeout, MetadataResult

logger = logging.getLogger("arm_backend.metadata.tvmaze")


def _base_url() -> str:
    return settings.ARM_TVMAZE_BASE_URL


def show_to_result(show: Any) -> MetadataResult | None:
    """One TVmaze show object → MetadataResult, or None without a name.
    Ids and the poster are normalised into the keys `external_ids_of` and
    `extract_poster_url` read; the raw object is kept alongside."""
    if not isinstance(show, dict):
        return None
    name = show.get("name")
    if not isinstance(name, str) or not name:
        return None
    premiered = show.get("premiered") or ""
    year = int(premiered[:4]) if isinstance(premiered, str) and premiered[:4].isdigit() else None
    payload: dict[str, Any] = dict(show)
    if show.get("id") is not None:
        payload["tvmaze_id"] = str(show["id"])
    raw_externals = show.get("externals")
    externals: dict[str, Any] = raw_externals if isinstance(raw_externals, dict) else {}
    imdb = externals.get("imdb")
    if isinstance(imdb, str) and imdb:
        payload["imdb_id"] = imdb
    tvdb = externals.get("thetvdb")
    if isinstance(tvdb, int) or (isinstance(tvdb, str) and tvdb):
        payload["tvdb_id"] = str(tvdb)
    raw_image = show.get("image")
    image: dict[str, Any] = raw_image if isinstance(raw_image, dict) else {}
    poster = image.get("medium") or image.get("original")
    if isinstance(poster, str) and poster.startswith("http"):
        payload["poster_url"] = poster
    return MetadataResult(title=name, year=year, kind="tv", payload=payload)


class TVMazeClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        try:
            r = await self._http.get(f"{_base_url()}{path}", params=params, follow_redirects=True)
        except httpx.TimeoutException as e:
            raise LookupTimeout("tvmaze timeout") from e
        except httpx.HTTPError as e:
            raise LookupError(f"tvmaze transport error: {e}") from e
        if r.status_code == 404:
            raise LookupError("tvmaze miss")
        if r.status_code != 200:
            raise LookupError(f"tvmaze status={r.status_code}")
        try:
            return r.json()
        except ValueError as e:
            raise LookupError("tvmaze malformed response") from e

    async def search_show(self, title: str) -> MetadataResult:
        result = show_to_result(await self._get("/singlesearch/shows", {"q": title}))
        if result is None:
            raise LookupError("tvmaze hit missing name")
        return result

    async def search_candidates(self, title: str, limit: int = 10) -> list[MetadataResult]:
        body = await self._get("/search/shows", {"q": title})
        if not isinstance(body, list):
            raise LookupError("tvmaze malformed response")
        out: list[MetadataResult] = []
        for entry in body:
            result = show_to_result(entry.get("show") if isinstance(entry, dict) else None)
            if result is not None:
                out.append(result)
            if len(out) >= limit:
                break
        return out

    async def lookup_by_imdb_id(self, imdb_id: str) -> MetadataResult:
        result = show_to_result(await self._get("/lookup/shows", {"imdb": imdb_id}))
        if result is None:
            raise LookupError("tvmaze lookup missing name")
        return result
