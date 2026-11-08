"""Sibling discs of the same show: which live jobs they are, and which seasons and episodes they hold."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_common import Job, JobStatus, Track
from arm_common.enums import MediaType
from arm_common.schemas import ExternalIds

from arm_backend.identity.episodes.continuity import SiblingDisc
from arm_backend.identity.ids import current_ids

# Jobs that never produced a disc's episodes; they are not siblings.
_DEAD_STATUSES = frozenset({JobStatus.FAILED, JobStatus.ABANDONED})


async def sibling_rows(session: AsyncSession, job: Job) -> list[tuple[Job, list[Track]]]:
    """Other live TV jobs of the same show (a shared show id, not the title
    string), with their tracks; a job with no external ids has none. Failed
    and abandoned jobs never hold episodes. Tracks load only for these."""
    ids = current_ids(job)
    if not ids.model_dump(exclude_none=True):
        return []
    stmt = select(Job).where(col(Job.media_type) == MediaType.TV)
    jobs = [
        j
        for j in (await session.execute(stmt)).scalars().all()
        if j.id != job.id and j.status not in _DEAD_STATUSES and _shares_id(ids, current_ids(j))
    ]
    if not jobs:
        return []
    tracks = (await session.execute(select(Track).where(col(Track.job_id).in_([j.id for j in jobs])))).scalars().all()
    return [(j, [t for t in tracks if t.job_id == j.id]) for j in jobs]


def _shares_id(ids: ExternalIds, other: ExternalIds) -> bool:
    theirs = other.model_dump(exclude_none=True)
    return any(value and theirs.get(key) == value for key, value in ids.model_dump(exclude_none=True).items())


def _held_numbers(sibling: Job, tracks: Sequence[Track], season: int) -> frozenset[int]:
    numbers: set[int] = set()
    for t in tracks:
        track_season = t.season if t.season is not None else sibling.season
        if track_season != season or t.episode_number is None:
            continue
        end = max(t.episode_number_end or t.episode_number, t.episode_number)
        numbers.update(range(t.episode_number, end + 1))
    return frozenset(numbers)


def sibling_discs(
    rows: Sequence[tuple[Job, list[Track]]], ids: ExternalIds, season: int, disc_number: int | None
) -> tuple[list[SiblingDisc], bool]:
    """Sibling discs of the same show (a shared non-empty external id) and
    season, with every episode number their resolved tracks hold.

    Only a sibling that is provably a different disc (both disc numbers known
    and different) claims its episodes. A sibling holding episodes that may be
    this same disc (an earlier rip of it, or either disc number unknown) is a
    conflict: returned as True so the result becomes a suggestion."""
    out: list[SiblingDisc] = []
    conflict = False
    for sibling, tracks in rows:
        if not _shares_id(ids, current_ids(sibling)):
            continue
        if sibling.season != season and not any(t.season == season for t in tracks):
            continue
        numbers = _held_numbers(sibling, tracks, season)
        if not numbers:
            continue
        if disc_number is not None and sibling.disc_number is not None and sibling.disc_number != disc_number:
            out.append(SiblingDisc(sibling.disc_number, numbers))
        else:
            conflict = True
    return out, conflict


def sibling_seasons(rows: Sequence[tuple[Job, list[Track]]], ids: ExternalIds) -> list[int]:
    """Seasons the sibling rows sharing an external id with `ids` hold (each
    job's season and every track's season), most frequent first, ties
    ascending."""
    counts: Counter[int] = Counter()
    for sibling, tracks in rows:
        if not _shares_id(ids, current_ids(sibling)):
            continue
        held = [sibling.season, *(t.season for t in tracks)]
        counts.update(season for season in held if season is not None)
    return sorted(counts, key=lambda season: (-counts[season], season))
