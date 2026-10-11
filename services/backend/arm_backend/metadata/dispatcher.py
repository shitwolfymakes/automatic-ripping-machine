import asyncio
import logging
import re
import unicodedata
from typing import Literal

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

# _call labels are "<provider>[_<operation>]"; arm_server's prefix is "arm".
_PROVIDER_BY_LABEL_PREFIX = {
    "tmdb": "tmdb",
    "omdb": "omdb",
    "arm": "arm_server",
    "musicbrainz": "musicbrainz",
}
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

# MusicBrainz 403s any User-Agent that doesn't follow their etiquette guide's
# `AppName/version ( contact )` shape. No longer operator-configurable (Config.
# musicbrainz_user_agent is dormant — see config_metadata.py); hardcoded here.
MUSICBRAINZ_USER_AGENT = "ARM/3.0.0 ( https://github.com/automatic-ripping-machine/automatic-ripping-machine )"


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
    def __init__(self, http: httpx.AsyncClient, *, omdb_api_key_override: str | None = None) -> None:
        self._http = http
        self._omdb_api_key_override = omdb_api_key_override

    async def aclose(self) -> None:
        await self._http.aclose()

    async def identify(
        self,
        scan: ScanResult,
        cfg: Config,
        *,
        title_hint: str | None = None,
        title_hint_is_tv: bool = False,
        prefer_tv: bool = False,
    ) -> MetadataResult | None:
        if scan.disc_type in (DiscType.DATA, DiscType.UNKNOWN):
            return None

        if scan.disc_type == DiscType.CD:
            return await self._identify_cd(scan)

        hit = await self._identify_video(
            scan, cfg, title_hint=title_hint, title_hint_is_tv=title_hint_is_tv, prefer_tv=prefer_tv
        )
        return await self._with_tmdb_ids(hit, cfg)

    async def _identify_cd(self, scan: ScanResult) -> MetadataResult | None:
        if not scan.musicbrainz_disc_id:
            return None
        client = MusicBrainzClient(MUSICBRAINZ_USER_AGENT, self._http)
        return await self._call("musicbrainz", client.lookup_disc_id(scan.musicbrainz_disc_id))

    async def _identify_video(
        self,
        scan: ScanResult,
        cfg: Config,
        *,
        title_hint: str | None = None,
        title_hint_is_tv: bool = False,
        prefer_tv: bool = False,
    ) -> MetadataResult | None:
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

        # Disc hints (bd_title / label, see arm_backend.identity) supply a
        # cleaner search title than the raw volume label — try it first, then
        # fall back to the normalized volume-label title. Empty and duplicate
        # (case-insensitive) candidates are skipped so a hint equal to the
        # label title doesn't double the provider calls. A hint that carries
        # a season claim (a season/box-set disc) is TV-shaped: search TMDb TV
        # before TMDb movie for THAT candidate only, so e.g. `LOST_S2D3`'s
        # hint title "lost" doesn't mismatch to TMDb's top movie hit. The
        # label-derived candidate keeps the existing movie-first order.
        # Compute the label candidate's (title, year) first so the hint
        # candidate — which has no year of its own — can be searched with the
        # same year filter (e.g. `ALIEN_1979` narrows the hint "alien" to
        # 1979 too, not an unfiltered search).
        label_title: str | None = None
        label_year: int | None = None
        if scan.volume_label:
            label_title, label_year = _normalize_volume_label(scan.volume_label)

        candidates: list[tuple[str, int | None, bool]] = []
        if title_hint and title_hint.strip():
            candidates.append((title_hint.strip(), label_year, title_hint_is_tv))
        if label_title:
            candidates.append((label_title, label_year, False))
        seen: set[str] = set()
        unique: list[tuple[str, int | None, bool]] = []
        for title, year, tv_first in candidates:
            key = title.casefold()
            if key not in seen:
                seen.add(key)
                unique.append((title, year, tv_first))
        if prefer_tv:
            # The disc itself is TV-shaped (arm_common.disc_shape): search TV for
            # every candidate before any movie, so one candidate's movie
            # fallback (e.g. a TMDb placeholder "Collection" movie) can't win
            # while another candidate would have found the series.
            for kind in ("tv", "movie"):
                for title, year, _ in unique:
                    hit = await self._search_kind(title, year, cfg, kind)
                    if hit is not None:
                        return hit
            return None
        for title, year, tv_first in unique:
            hit = await self._search_title(title, year, cfg, tv_first=tv_first)
            if hit is not None:
                return hit
        return None

    async def _search_kind(
        self, title: str, year: int | None, cfg: Config, kind: Literal["movie", "tv"]
    ) -> MetadataResult | None:
        """One kind only: TMDb (movie or TV) when keyed, then OMDb of that kind."""
        if cfg.tmdb_api_key:
            tmdb = TMDBClient(cfg.tmdb_api_key, self._http)
            search = tmdb.search_tv(title) if kind == "tv" else tmdb.search_movie(title, year)
            hit = await self._call(f"tmdb_{kind}", search)
            if hit is not None:
                return hit
        omdb_key = self._omdb_api_key_override or cfg.omdb_api_key
        if omdb_key:
            omdb = OMDBClient(omdb_key, self._http)
            return await self._call(f"omdb_{kind}", omdb.lookup_by_title(title, year, kind=kind))
        return None

    async def _search_title(
        self, title: str, year: int | None, cfg: Config, *, tv_first: bool = False
    ) -> MetadataResult | None:
        if cfg.tmdb_api_key:
            tmdb = TMDBClient(cfg.tmdb_api_key, self._http)
            if tv_first:
                hit = await self._call("tmdb_tv", tmdb.search_tv(title))
                if hit is not None:
                    return hit
                hit = await self._call("tmdb_movie", tmdb.search_movie(title, year))
                if hit is not None:
                    return hit
            else:
                hit = await self._call("tmdb_movie", tmdb.search_movie(title, year))
                if hit is not None:
                    return hit
                hit = await self._call("tmdb_tv", tmdb.search_tv(title))
                if hit is not None:
                    return hit

        omdb_key = self._omdb_api_key_override or cfg.omdb_api_key
        if omdb_key:
            omdb = OMDBClient(omdb_key, self._http)
            # A season-shaped hint is TV, not a movie: an OMDb-only install
            # (no TMDb key) must search OMDb `type=series` for it, or a hint
            # like "lost" silently identifies as the movie "Lost" (finding 1).
            kind: Literal["movie", "tv"] = "tv" if tv_first else "movie"
            hit = await self._call(f"omdb_{kind}", omdb.lookup_by_title(title, year, kind=kind))
            if hit is not None:
                return hit

        return None

    async def identify_from_imdb(self, imdb_id: str, cfg: Config) -> MetadataResult | None:
        """Exact-ID identify for a TheDiscDB-matched disc. TMDb's /find
        endpoint resolves an IMDb id for both movies and TV; requires a TMDb
        key. Returns None (caller falls back to fuzzy identify) otherwise."""
        if not imdb_id or not cfg.tmdb_api_key:
            return None
        tmdb = TMDBClient(cfg.tmdb_api_key, self._http)
        hit = await self._call("tmdb_find_imdb", tmdb.find_by_imdb_id(imdb_id))
        if hit is not None:
            hit.payload.setdefault("imdb_id", imdb_id)
        return await self._with_tmdb_ids(hit, cfg)

    async def _with_tmdb_ids(self, hit: MetadataResult | None, cfg: Config) -> MetadataResult | None:
        """Fill a TMDb hit's IMDb / TVDB ids (one `external_ids` call) so the
        stored identity lets every episode source find the show (spec 3.4).
        Ids already in the payload win; a failed or timed-out call (bounded
        by PROVIDER_TIMEOUT_SECONDS) changes nothing."""
        if hit is None or hit.provider != "tmdb" or hit.kind not in ("movie", "tv") or not cfg.tmdb_api_key:
            return hit
        tmdb_id = hit.payload.get("id")
        if tmdb_id is None:
            return hit
        try:
            found = await asyncio.wait_for(
                TMDBClient(cfg.tmdb_api_key, self._http).get_external_id_map(tmdb_id, hit.kind),
                timeout=PROVIDER_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.info("metadata.tmdb_external_ids timeout id=%s", tmdb_id)
            return hit
        for key, value in found.items():
            hit.payload.setdefault(key, value)
        return hit

    async def _call(self, label: str, coro) -> MetadataResult | None:  # type: ignore[no-untyped-def]
        try:
            result: MetadataResult | None = await asyncio.wait_for(coro, timeout=PROVIDER_TIMEOUT_SECONDS)
            if result is not None:
                # "tmdb_movie"/"tmdb_tv"/"tmdb_find_imdb" → "tmdb"; the
                # canonical name keys provider_raw and identity.provider.
                result.provider = _PROVIDER_BY_LABEL_PREFIX.get(label.split("_", 1)[0], label)
            return result
        except asyncio.TimeoutError:
            logger.info("metadata.%s timeout", label)
            return None
        except LookupError as e:
            logger.info("metadata.%s miss: %s", label, e)
            return None
