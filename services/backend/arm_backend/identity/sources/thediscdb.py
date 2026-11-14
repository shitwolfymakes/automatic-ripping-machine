"""TheDiscDB disc-map source: join a snapshot match to the MakeMKV scan and
propose per-title identity (tier 2).

Join keys, in order: SourceFile == ScanTitle.source_file (case-insensitive);
else duration within +-2s IF exactly one scan title with source_file=None is
in the window (ambiguity -> no join; a wrong label is worse than no label).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime
from typing import Any, Literal

from arm_common.enums import TrackRole
from arm_common.schemas import ScanResult, ScanTitle
from arm_common.schemas.identity import JobClaim, SourceClaims, TrackClaim

from arm_backend.identity.sources.thediscdb_snapshot import DiscMatch
from arm_backend.metadata.base import MetadataResult

SOURCE_ID = "thediscdb"
DURATION_WINDOW_SECONDS = 2
_SELECT_TYPES = {"MainMovie", "Episode"}
_EXTRA_TYPES = {"Extra", "Featurette", "DeletedScene", "Interview", "BehindTheScenes", "Short"}


def role_for_disc_type(type_name: str) -> TrackRole:
    if type_name == "MainMovie":
        return TrackRole.MAIN
    if type_name == "Episode":
        return TrackRole.EPISODE
    if type_name == "Trailer":
        return TrackRole.TRAILER
    if type_name in _EXTRA_TYPES:
        return TrackRole.EXTRA
    return TrackRole.OTHER


def parse_duration(text: str) -> int | None:
    """ "H:MM:SS" or "MM:SS" -> seconds; None on anything else."""
    if not text:
        return None
    parts = text.split(":")
    if not 2 <= len(parts) <= 3:
        return None
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    return nums[0] * 3600 + nums[1] * 60 + nums[2]


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() != "" else None
    except TypeError, ValueError:
        return None


def _valid_entries(match: DiscMatch) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    """Each dict entry of the disc's `Titles` with its `Item` (an empty dict
    when missing or not a dict)."""
    for entry in match.disc.get("Titles") or []:
        if not isinstance(entry, dict):
            continue
        item = entry.get("Item") or {}
        if not isinstance(item, dict):
            item = {}
        yield entry, item


def _join_scan_title(entry: dict[str, Any], scan: ScanResult, by_source_file: dict[str, ScanTitle]) -> ScanTitle | None:
    """The scan title an entry describes: the one with its source file, else
    the one scan title without a source file within DURATION_WINDOW_SECONDS
    of its duration; None when neither joins."""
    source_file = str(entry.get("SourceFile") or "").lower()
    scan_title = by_source_file.get(source_file)
    if scan_title is not None:
        return scan_title
    want = parse_duration(str(entry.get("Duration") or ""))
    if want is None:
        return None
    candidates = [
        t for t in scan.titles if t.source_file is None and abs(t.duration_seconds - want) <= DURATION_WINDOW_SECONDS
    ]
    return candidates[0] if len(candidates) == 1 else None


def _type_name(item: dict[str, Any]) -> str:
    """The item's TheDiscDB type, `Unknown` when unset."""
    return str(item.get("Type") or "Unknown")


def _track_fields(entry: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    """The track-claim fields an entry proposes: role, episode name, season,
    episode, file name and selection."""
    type_name = _type_name(item)
    fields: dict[str, Any] = {"role": role_for_disc_type(type_name)}
    if item.get("Title"):
        fields["episode_name"] = str(item["Title"])
    season = _int_or_none(item.get("Season"))
    if season is not None:
        fields["season"] = season
    episode = _int_or_none(item.get("Episode"))
    if episode is not None:
        fields["episode"] = episode
    if entry.get("Comment"):
        fields["filename"] = str(entry["Comment"])
    if type_name in _SELECT_TYPES:
        fields["selected"] = True
    return fields


def _episode_season(item: dict[str, Any]) -> int | None:
    """The season of an `Episode` item, else None."""
    return _int_or_none(item.get("Season")) if _type_name(item) == "Episode" else None


def _job_claim(match: DiscMatch, episode_seasons: set[int]) -> JobClaim:
    """The job claim: the season when every matched episode shares one, and
    the disc number when the release has a single season."""
    job = JobClaim()
    if len(episode_seasons) == 1:
        job.season = next(iter(episode_seasons))
    disc_index = match.disc.get("Index")
    if match.release_seasons and len(match.release_seasons) == 1 and isinstance(disc_index, int):
        job.disc_number = disc_index
    return job


def _contributors(match: DiscMatch) -> list[str]:
    """The names of the release's contributors."""
    return [
        str(c.get("Name")) for c in (match.release.get("Contributors") or []) if isinstance(c, dict) and c.get("Name")
    ]


def build_claims(match: DiscMatch, scan: ScanResult, *, now: datetime) -> SourceClaims:
    by_source_file = {t.source_file.lower(): t for t in scan.titles if t.source_file}
    tracks: dict[str, TrackClaim] = {}
    episode_seasons: set[int] = set()
    for entry, item in _valid_entries(match):
        scan_title = _join_scan_title(entry, scan, by_source_file)
        if scan_title is None:
            continue
        ref = str(scan_title.index)
        if ref in tracks:
            continue  # first disc entry wins; don't flip-flop on dupes
        tracks[ref] = TrackClaim(**_track_fields(entry, item))
        season = _episode_season(item)
        if season is not None:
            episode_seasons.add(season)
    return SourceClaims(
        run_at=now,
        status="ok",
        job=_job_claim(match, episode_seasons),
        tracks=tracks,
        extra={
            "release_slug": match.release_slug,
            "title_slug": match.title_slug,
            "kind": match.kind,
            # Community credit (spec): who contributed this disc layout.
            "contributors": _contributors(match),
        },
    )


def external_imdb_id(match: DiscMatch) -> str | None:
    ids = match.metadata.get("ExternalIds")
    if not isinstance(ids, dict):
        return None
    imdb = ids.get("Imdb")
    return str(imdb) if imdb else None


def release_kind(match: DiscMatch) -> Literal["movie", "tv"]:
    """TheDiscDB's top-level directory names the kind (`movies` / `series`)."""
    return "movie" if str(match.kind or "").lower().startswith("movie") else "tv"


# A release-year suffix on a title slug (`round-midnight-1986`). Capped at
# 2029, the same bound and reasoning as the dispatcher's
# `_HINT_YEAR_SUFFIX_RE`: a title that genuinely ends in a later number
# (`blade-runner-2049`) must never be shortened to "Blade Runner".
_SLUG_YEAR_RE = re.compile(r"-(19\d{2}|20[0-2]\d)$")


def release_identity(match: DiscMatch) -> tuple[str | None, int | None]:
    """The release's own title and year: the title metadata when present,
    else derived from the title slug (`round-midnight-1986`)."""
    title = match.metadata.get("Title")
    year = _int_or_none(match.metadata.get("Year"))
    if isinstance(title, str) and title.strip():
        return title.strip(), year
    slug = str(match.title_slug or "").strip()
    if not slug:
        return None, None
    m = _SLUG_YEAR_RE.search(slug)
    # A trailing number is the release year only when it is not the tail of the
    # title itself. TheDiscDB's own Year settles it when the snapshot has one
    # (`blade-runner-2049` under Year=2017 keeps its 2049); without one the
    # suffix is read as the year, which is all the slug can tell us.
    if m and (year is None or int(m.group(1)) == year):
        year = year if year is not None else int(m.group(1))
        slug = slug[: m.start()]
    words = [w for w in slug.split("-") if w]
    return (" ".join(w.capitalize() for w in words) or None), year


def release_result(match: DiscMatch, imdb_id: str) -> MetadataResult | None:
    """The disc named by its TheDiscDB release alone (no online call);
    None when the release has no usable title."""
    title, year = release_identity(match)
    if not title:
        return None
    return MetadataResult(
        title=title,
        year=year,
        kind=release_kind(match),
        payload={"imdb_id": imdb_id, "thediscdb_release": match.release_slug},
        provider="thediscdb",
    )
