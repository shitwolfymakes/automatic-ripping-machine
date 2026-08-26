"""Join a TheDiscDB disc map to a MakeMKV scan and stamp Track rows.

Join keys, in order: SourceFile == ScanTitle.source_file (case-insensitive);
else duration within ±2s IF exactly one scan title with source_file=None is in
the window (ambiguity -> no join; a wrong label is worse than no label).
Duration fallback only considers titles with source_file=None to prevent
mis-joins when SourceFile naming skews from expected values.

The map is stored JSON-safe in job.metadata_json["thediscdb"] at identify
time, then applied to Track rows wherever tracks are created (identify's
review path and rip-start) — apply_map is idempotent and only fills
operator-empty fields, so re-running never clobbers operator edits.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.thediscdb.snapshot import DiscMatch
from arm_common import Job, Track
from arm_common.schemas import ScanResult

logger = logging.getLogger(__name__)

DURATION_WINDOW_SECONDS = 2
# TheDiscDB Item.Type values that should be selected (excluded=False).
_SELECT_TYPES = {"MainMovie", "Episode"}


def parse_duration(text: str) -> int | None:
    """"H:MM:SS" or "MM:SS" -> seconds; None on anything else."""
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
    except (TypeError, ValueError):
        return None


def build_map(match: DiscMatch, scan: ScanResult) -> dict[str, Any]:
    """Produce the JSON-safe match record keyed by track source_ref."""
    by_source_file = {
        t.source_file.lower(): t for t in scan.titles if t.source_file
    }
    matched: dict[str, dict[str, Any]] = {}
    for entry in match.disc.get("Titles") or []:
        if not isinstance(entry, dict):
            continue
        item = entry.get("Item") or {}
        if not isinstance(item, dict):
            item = {}
        source_file = str(entry.get("SourceFile") or "").lower()
        scan_title = by_source_file.get(source_file)
        if scan_title is None:
            # Duration fallback: unique scan title within ±2s.
            want = parse_duration(str(entry.get("Duration") or ""))
            if want is None:
                continue
            candidates = [
                t for t in scan.titles
                if t.source_file is None and abs(t.duration_seconds - want) <= DURATION_WINDOW_SECONDS
            ]
            if len(candidates) != 1:
                continue
            scan_title = candidates[0]
        ref = str(scan_title.index)
        if ref in matched:
            continue  # first disc entry wins; don't flip-flop on dupes
        matched[ref] = {
            "type": str(item.get("Type") or "Unknown"),
            "title": item.get("Title"),
            "season": _int_or_none(item.get("Season")),
            "episode": _int_or_none(item.get("Episode")),
            "filename": entry.get("Comment"),
        }
    return {
        "release_slug": match.release_slug,
        "title_slug": match.title_slug,
        "kind": match.kind,
        # Community credit (spec): who contributed this disc layout.
        "contributors": [
            str(c.get("Name")) for c in (match.release.get("Contributors") or []) if isinstance(c, dict) and c.get("Name")
        ],
        "matched": matched,
    }


def external_imdb_id(match: DiscMatch) -> str | None:
    ids = match.metadata.get("ExternalIds")
    if not isinstance(ids, dict):
        return None
    imdb = ids.get("Imdb")
    return str(imdb) if imdb else None


async def apply_map(session: AsyncSession, job: Job) -> int:
    """Stamp the stored map onto the job's Track rows. Idempotent; returns
    the number of tracks updated. Never raises on malformed map data."""
    record = (job.metadata_json or {}).get("thediscdb")
    if not isinstance(record, dict):
        return 0
    matched = record.get("matched")
    if not isinstance(matched, dict) or not matched:
        return 0
    tracks = (
        (await session.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all()
    )
    updated = 0
    for track in tracks:
        entry = matched.get(track.source_ref)
        if not isinstance(entry, dict):
            continue
        track.role = str(entry.get("type") or "Unknown")
        track.role_source = "thediscdb"
        if entry.get("title") and not track.episode_name:
            track.episode_name = str(entry["title"])
        season = _int_or_none(entry.get("season"))
        if season is not None and track.season is None:
            track.season = season
        episode = _int_or_none(entry.get("episode"))
        if episode is not None and track.episode_number is None:
            track.episode_number = episode
        if entry.get("filename") and not track.custom_filename:
            track.custom_filename = str(entry["filename"])
        if entry.get("type") in _SELECT_TYPES:
            track.excluded = False
        session.add(track)
        updated += 1
    if updated:
        await session.flush()
        logger.info("thediscdb: applied map to %d tracks job_id=%s", updated, job.id)
    return updated
