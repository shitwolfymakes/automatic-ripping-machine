"""TheDiscDB disc-map source: join a snapshot match to the MakeMKV scan and
propose per-title identity (tier 2).

Join keys, in order: SourceFile == ScanTitle.source_file (case-insensitive);
else duration within +-2s IF exactly one scan title with source_file=None is
in the window (ambiguity -> no join; a wrong label is worse than no label).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from arm_common.enums import TrackRole
from arm_common.schemas import ScanResult
from arm_common.schemas.identity import SourceClaims, TrackClaim

from arm_backend.identity.sources.thediscdb_snapshot import DiscMatch

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


def build_claims(match: DiscMatch, scan: ScanResult, *, now: datetime) -> SourceClaims:
    by_source_file = {t.source_file.lower(): t for t in scan.titles if t.source_file}
    tracks: dict[str, TrackClaim] = {}
    for entry in match.disc.get("Titles") or []:
        if not isinstance(entry, dict):
            continue
        item = entry.get("Item") or {}
        if not isinstance(item, dict):
            item = {}
        source_file = str(entry.get("SourceFile") or "").lower()
        scan_title = by_source_file.get(source_file)
        if scan_title is None:
            want = parse_duration(str(entry.get("Duration") or ""))
            if want is None:
                continue
            candidates = [
                t
                for t in scan.titles
                if t.source_file is None and abs(t.duration_seconds - want) <= DURATION_WINDOW_SECONDS
            ]
            if len(candidates) != 1:
                continue
            scan_title = candidates[0]
        ref = str(scan_title.index)
        if ref in tracks:
            continue  # first disc entry wins; don't flip-flop on dupes
        type_name = str(item.get("Type") or "Unknown")
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
        tracks[ref] = TrackClaim(**fields)
    return SourceClaims(
        run_at=now,
        status="ok",
        tracks=tracks,
        extra={
            "release_slug": match.release_slug,
            "title_slug": match.title_slug,
            "kind": match.kind,
            # Community credit (spec): who contributed this disc layout.
            "contributors": [
                str(c.get("Name"))
                for c in (match.release.get("Contributors") or [])
                if isinstance(c, dict) and c.get("Name")
            ],
        },
    )


def external_imdb_id(match: DiscMatch) -> str | None:
    ids = match.metadata.get("ExternalIds")
    if not isinstance(ids, dict):
        return None
    imdb = ids.get("Imdb")
    return str(imdb) if imdb else None
