"""Decides which rip preset and min-length override govern a job's rip, from its routed session."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.session_routing import resolve_routed_session_id
from arm_common import DiscType, Job, RipPreset, Session

logger = logging.getLogger("arm_backend.rip_preset_resolution")

_DEFAULT_RIP_PRESET_BY_DISC_TYPE: dict[DiscType, str] = {
    DiscType.DVD: "rpr_builtin_movie_archive",
    DiscType.BLURAY: "rpr_builtin_movie_archive",
    DiscType.CD: "rpr_builtin_music_standard",
    DiscType.DATA: "rpr_builtin_data_copy",
}


class RipPresetUnavailable(Exception):
    """resolve_rip_preset_for_job cannot produce a preset for this job.

    `reason` lets routes keep their distinct responses: "no_default" is a 422
    (unknown disc type — the ripper must not retry), "not_seeded" is a 500
    (deployment bug — seeding may fix it, retryable).
    """

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


async def load_routed_session(db: AsyncSession, job: Job) -> Session | None:
    """Resolve + load the job's ROUTED session row in one shot.

    The single query rip-start (and resume) needs — every other
    resolver in this module is now a pure derivation over the `Session |
    None` this returns, so a request thread only ever pays for one
    `resolve_routed_session_id` call and one `Session` SELECT, instead of
    re-resolving from scratch per field. Returns None when nothing routes,
    or when a routed id's Session row is gone (deleted between trigger and
    rip) — logged once here so callers don't each emit their own warning.
    """
    routed_id = await resolve_routed_session_id(db, job)
    if routed_id is None:
        return None
    sess = (await db.execute(select(Session).where(col(Session.id) == routed_id))).scalar_one_or_none()
    if sess is None:
        logger.warning(
            "routed session %s missing for job_id=%s; falling back to disc-type default",
            routed_id,
            job.id,
        )
    return sess


def rip_preset_id_from_session(sess: Session | None, disc_type: DiscType) -> str:
    """Pure derivation: routed session's preset id, else the disc-type default."""
    if sess is not None:
        return sess.rip_preset_id
    preset_id = _DEFAULT_RIP_PRESET_BY_DISC_TYPE.get(disc_type)
    if preset_id is None:
        raise RipPresetUnavailable("no_default", f"no default rip preset for disc_type={disc_type.value}")
    return preset_id


def min_length_override_from_session(sess: Session | None) -> int | None:
    """Pure derivation: `sess.overrides_json["min_length_seconds"]` when a
    valid non-negative int, else None (defensive against bad/legacy data)."""
    if sess is None or not sess.overrides_json:
        return None
    raw = sess.overrides_json.get("min_length_seconds")
    if isinstance(raw, bool):  # bool is an int subclass — reject explicitly
        return None
    if isinstance(raw, int) and raw >= 0:
        return raw
    return None


async def resolve_rip_preset_id_for_job(db: AsyncSession, job: Job) -> str:
    """The one place that decides WHICH rip preset governs a job's rip.

    Every chooser — rip-start, resume, the review-gate track persist — MUST resolve through
    here so a held disc and an unattended one rip the same track set.

    The ROUTED session's rip preset wins — the disc-type default is
    the fallback for jobs no session routes to (auto-rips on drives without
    a default). A routed id whose Session row is gone (deleted between
    trigger and rip) also falls back rather than failing the rip.

    Raises RipPresetUnavailable("no_default") when nothing resolves for the
    disc type (422 at the routes — the ripper must not retry). Does NOT load
    the preset row: rip-start's crash-resume and status-check paths answer
    without it, and "not_seeded" only surfaces when track selection actually
    needs the preset.

    Single-caller convenience wrapper over `load_routed_session` +
    `rip_preset_id_from_session` — rip-start/resume call those two
    directly so one request only resolves the routed session once.
    """
    sess = await load_routed_session(db, job)
    return rip_preset_id_from_session(sess, job.disc_type)


async def resolve_rip_preset_for_job(db: AsyncSession, job: Job) -> RipPreset:
    """`resolve_rip_preset_id_for_job` plus the row load.

    Additionally raises RipPresetUnavailable("not_seeded") when the resolved
    id has no row (deployment bug; 500 at the routes, retryable).
    """
    preset_id = await resolve_rip_preset_id_for_job(db, job)
    preset = (await db.execute(select(RipPreset).where(col(RipPreset.id) == preset_id))).scalar_one_or_none()
    if preset is None:
        raise RipPresetUnavailable("not_seeded", f"built-in rip preset {preset_id} not seeded")
    return preset


async def resolve_min_length_override(db: AsyncSession, job: Job) -> int | None:
    """Look up `Session.overrides_json["min_length_seconds"]` for the job's
    ROUTED session (explicit per-rip choice, else the compatibility-gated
    drive default, else a `session_routes` match - see
    `resolve_routed_session_id`), returning None when no override applies.
    The ripper falls back to its host-side `ARM_MIN_LENGTH_SECONDS` baseline
    when this is None.

    Single-caller convenience wrapper over `load_routed_session` +
    `min_length_override_from_session` — see `resolve_rip_preset_id_for_job`.
    """
    sess = await load_routed_session(db, job)
    return min_length_override_from_session(sess)
