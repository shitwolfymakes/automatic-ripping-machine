"""Which session is routed to a job (the pending choice, the compatibility-gated drive default, then
`session_routes`), and whether rip-complete may queue it unattended."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_common import Config, DiscType, Drive, Job, MediaType, Session, SessionRoute

logger = logging.getLogger("arm_backend.session_routing")


def media_types_compatible(job_mt: MediaType, sess_mt: MediaType) -> bool:
    """Whether a session of `sess_mt` can meaningfully apply to a job of `job_mt`.

    movie and tv are the same track kind (`TrackKind.VIDEO_TITLE`, see
    `_track_kinds_for_media` in transcode_apply.py) - a TV session applied to
    a job that got identified as a movie (or vice versa) still fans out real
    tasks. An iso/data session consumes a dump of any video disc (or another
    data disc) - no identified job is ever `iso`, so an iso-typed
    drive-default/route must still apply to movie/tv/data jobs. Music is
    strictly music: never compatible with anything else.
    """
    if job_mt == sess_mt:
        return True
    video = {MediaType.MOVIE, MediaType.TV}
    if sess_mt in video and job_mt in video:
        return True
    if sess_mt in (MediaType.ISO, MediaType.DATA) and job_mt in video | {MediaType.DATA}:
        return True
    return False


def _pending_session_id(job: Job) -> str | None:
    return job.pending_session_id or None


def routing_media_type(job: Job) -> MediaType | None:
    """The media type routing keys on: the identified kind, else what the disc
    type alone says. An audio CD is music whether or not MusicBrainz knew it,
    so an unidentified CD still reaches the music routes and the drive
    default's compatibility gate instead of a video default."""
    if job.media_type is not None:
        return job.media_type
    if job.disc_type == DiscType.CD:
        return MediaType.MUSIC
    return None


async def resolve_routed_session_id(db: AsyncSession, job: Job) -> str | None:
    """Which session is ROUTED to this job.

    Resolution order (single source of truth - rip-start's preset choice and
    the naming preview resolve through this same helper so neither can drift
    from the apply path):
      1. `job.pending_session_id` - explicit per-rip choice.
      2. `drive.default_session_id` - the persistent per-drive default, but
         ONLY when it's compatibility-gated: the drive default wins when
         the routing media type (`routing_media_type`: the job's
         media_type, or music for a CD) is None (nothing to disagree with
         yet) OR the
         drive-default session's media_type is `media_types_compatible`
         with the job's. Otherwise (e.g. a movie drive default on a music CD
         job) it's skipped in favor of steps 3-4 - a drive default must not
         permanently swallow a media type it was never meant for. A
         dangling `default_session_id` (the session row no longer exists)
         also falls through to routes, logged at DEBUG.
      3. `session_routes` row matching `(job.media_type, job.disc_type)` exactly.
      4. `session_routes` wildcard row matching `(job.media_type, NULL)`.
      5. None.
    Steps 3-4 are skipped when the routing media type is None (a
    never-identified non-CD disc) - a route is keyed on media_type, so there
    is nothing to match. No
    `auto_transcode_on_idle` gating: routing shapes the rip and the preview;
    whether rip-complete may QUEUE the routed session unattended is
    `auto_apply_allowed`'s question. Returns None when nothing routes.
    """
    pending = _pending_session_id(job)
    if pending is not None:
        return pending
    media_type = routing_media_type(job)
    drive = (await db.execute(select(Drive).where(col(Drive.id) == job.drive_id))).scalar_one_or_none()
    if drive is not None and drive.default_session_id is not None:
        if media_type is None:
            return drive.default_session_id
        default_sess = (
            await db.execute(select(Session).where(col(Session.id) == drive.default_session_id))
        ).scalar_one_or_none()
        if default_sess is None:
            logger.debug(
                "resolve_routed_session_id: drive default session_id=%s missing for drive_id=%s; "
                "falling through to routes",
                drive.default_session_id,
                drive.id,
            )
        elif default_sess.media_type is None or media_types_compatible(media_type, default_sess.media_type):
            return drive.default_session_id
        # else: incompatible drive default — fall through to session_routes.

    if media_type is None:
        return None

    return await route_session_id_for(db, media_type, job.disc_type)


async def route_session_id_for(db: AsyncSession, media_type: MediaType, disc_type: DiscType | None) -> str | None:
    """SessionRoute lookup: the exact (media_type, disc_type) route, then the
    (media_type, NULL) wildcard. Shared by job routing and the setup
    walkthrough's read-only disc-routes summary."""
    routes = (await db.execute(select(SessionRoute).where(col(SessionRoute.media_type) == media_type))).scalars().all()
    exact = next((r for r in routes if r.disc_type == disc_type), None)
    if exact is not None:
        return exact.session_id
    wildcard = next((r for r in routes if r.disc_type is None), None)
    if wildcard is not None:
        return wildcard.session_id
    return None


async def auto_apply_allowed(db: AsyncSession, job: Job) -> bool:
    """May rip-complete queue the ROUTED session (`resolve_routed_session_id`
    — pending choice, else the compatibility-gated drive default, else
    `session_routes`) unattended?

    An explicit per-rip choice is the user opting in for that one rip and
    bypasses the flag; everything else (drive default or a route) needs
    `auto_transcode_on_idle`.
    """
    if _pending_session_id(job) is not None:
        return True
    config_row = (await db.execute(select(Config).where(col(Config.id) == 1))).scalar_one_or_none()
    return config_row is not None and bool(config_row.auto_transcode_on_idle)
