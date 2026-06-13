import asyncio
import logging
import re
import unicodedata

import httpx

from arm_backend.metadata.arm_server import ArmServerClient
from arm_backend.metadata.base import LookupError, MetadataResult
from arm_backend.metadata.musicbrainz import MusicBrainzClient
from arm_backend.metadata.omdb import OMDBClient
from arm_backend.metadata.tmdb import TMDBClient
from arm_common import Config, DiscType
from arm_common.schemas import ScanResult

logger = logging.getLogger("arm_backend.metadata.dispatcher")

PROVIDER_TIMEOUT_SECONDS = 8.0
DISPATCH_TIMEOUT_SECONDS = 25.0

_YEAR_SUFFIX_RE = re.compile(r"[\s_\-.]*\(?\d{4}\)?\s*$")
# DVDs commonly bake the broadcast standard into the volume label
# (e.g. `THE_MATRIX_NTSC` or `MOVIE_NTSC_1999`). It's noise for title
# matching — strip it before the underscore-to-space pass so OMDB/TMDB
# searches don't see "MATRIX NTSC".
_NTSC_TOKEN_RE = re.compile(r"_NTSC(?=[_.\s\-]|$)", re.IGNORECASE)
# Blu-rays bake disc-format branding into the title/label the same way.
# v2 stripped a fixed set of "Blu-rayTM" suffixes off the BDMV disc title
# (see arm/ripper/main/identify.py); reproduce that here generically so a
# label like `MOVIE_BLU_RAY`, `Movie - Blu-rayTM`, or `BLURAY` loses the
# branding before lookup. The optional `tm|™` covers the trademark glyph
# in either pre- or post-ASCII-normalised form.
_BLURAY_BRANDING_RE = re.compile(r"[\s_\-]*blu[\s_\-]?ray(?:\s*(?:tm|™))?", re.IGNORECASE)
# `_BD` (Blu-ray Disc) token, mirroring the `_NTSC` treatment.
_BD_TOKEN_RE = re.compile(r"_BD(?=[_.\s\-]|$)", re.IGNORECASE)


def _normalize_volume_label(label: str) -> tuple[str, int | None]:
    # Fold compatibility glyphs WITHOUT dropping non-ASCII: NFKC turns
    # "Blu-ray™" → "Blu-rayTM" and full-width forms → half-width, but keeps
    # accents and non-Latin scripts intact ("Amélie", "Война и мир", "君の名は"
    # all survive) so worldwide titles still reach the providers. This is
    # deliberately NOT the NFKD→ASCII strip `slugify` uses — that targets
    # ASCII filename tokens; here we must preserve the real searchable title.
    cleaned = unicodedata.normalize("NFKC", label)
    cleaned = _NTSC_TOKEN_RE.sub("", cleaned)
    cleaned = _BD_TOKEN_RE.sub("", cleaned)
    cleaned = _BLURAY_BRANDING_RE.sub("", cleaned)
    cleaned = cleaned.replace("_", " ").replace(".", " ").strip()
    year: int | None = None
    m = re.search(r"(\d{4})", cleaned)
    if m:
        candidate = int(m.group(1))
        if 1900 <= candidate <= 2100:
            year = candidate
    cleaned = _YEAR_SUFFIX_RE.sub("", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned, year


class MetadataDispatcher:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def aclose(self) -> None:
        await self._http.aclose()

    async def identify(self, scan: ScanResult, cfg: Config) -> MetadataResult | None:
        if scan.disc_type in (DiscType.DATA, DiscType.UNKNOWN):
            return None

        if scan.disc_type == DiscType.CD:
            return await self._identify_cd(scan, cfg)

        return await self._identify_video(scan, cfg)

    async def _identify_cd(self, scan: ScanResult, cfg: Config) -> MetadataResult | None:
        if not scan.musicbrainz_disc_id or not cfg.musicbrainz_user_agent:
            return None
        client = MusicBrainzClient(cfg.musicbrainz_user_agent, self._http)
        return await self._call("musicbrainz", client.lookup_disc_id(scan.musicbrainz_disc_id))

    async def _identify_video(self, scan: ScanResult, cfg: Config) -> MetadataResult | None:
        # 1337server first when we have a DVD CRC64. This is the
        # community-maintained crc64 → title DB; a hit beats fuzzy
        # title matching on TMDB/OMDB because the fingerprint is unique
        # to the disc and there's no false-positive risk.
        crc64 = next(
            (fp.value for fp in scan.fingerprints if fp.algo == "crc64" and fp.value),
            None,
        )
        if crc64:
            arm = ArmServerClient(self._http)
            hit = await self._call("arm_server", arm.lookup_by_crc64(crc64))
            if hit is not None:
                return hit

        if not scan.volume_label:
            return None
        title, year = _normalize_volume_label(scan.volume_label)
        if not title:
            return None

        if cfg.tmdb_api_key:
            tmdb = TMDBClient(cfg.tmdb_api_key, self._http)
            hit = await self._call("tmdb_movie", tmdb.search_movie(title, year))
            if hit is not None:
                return hit
            hit = await self._call("tmdb_tv", tmdb.search_tv(title))
            if hit is not None:
                return hit

        omdb_key = cfg.omdb_api_key
        if omdb_key:
            omdb = OMDBClient(omdb_key, self._http)
            hit = await self._call("omdb_movie", omdb.lookup_by_title(title, year, kind="movie"))
            if hit is not None:
                return hit

        return None

    async def _call(self, label: str, coro) -> MetadataResult | None:  # type: ignore[no-untyped-def]
        try:
            return await asyncio.wait_for(coro, timeout=PROVIDER_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.info("metadata.%s timeout", label)
            return None
        except LookupError as e:
            logger.info("metadata.%s miss: %s", label, e)
            return None
