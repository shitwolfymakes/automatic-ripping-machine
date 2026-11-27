"""What a rip is frozen to at Start: in a per-title rip, an unticked title is never read, so its track is SKIPPED."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_common import Job, RipInvocation, Track, TrackKind, TrackStatus


def tracks_to_skip(tracks: Sequence[Track], invocation: RipInvocation) -> list[Track]:
    """The tracks a rip started with `invocation` will not read: per-title only, the unticked, still-queued video
    titles. `mkv all` writes every eligible title whatever is ticked, so it skips none."""
    if invocation is not RipInvocation.PER_TITLE:
        return []
    return [t for t in tracks if t.excluded and t.status == TrackStatus.QUEUED and t.kind == TrackKind.VIDEO_TITLE]


async def skip_unticked(session: AsyncSession, job: Job, invocation: RipInvocation) -> list[Track]:
    """Mark the job's `tracks_to_skip` SKIPPED and flush; the caller commits. Idempotent: a SKIPPED track is no
    longer queued."""
    tracks = (await session.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all()
    skipped = tracks_to_skip(tracks, invocation)
    for track in skipped:
        track.status = TrackStatus.SKIPPED
        session.add(track)
    await session.flush()
    return skipped
