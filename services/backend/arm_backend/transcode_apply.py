"""Apply-time fan-out helpers: resolve output paths + detect collisions.

`compute_outputs` is a pure function: given a `Job`, its `Track` rows, the
`Session`, and (optional) `TranscodePreset`, it returns the list of resolved
output paths — one per track that should produce a transcode task. Empty
tokens raise `TemplateValidationError` so callers can surface a 422 instead
of writing `Iron Man () - .mkv` to disk.

`find_collisions` is the I/O step: queries the live `transcode_tasks` table
for any matching `output_path` in queued/in_progress/done state, then stats
each candidate path under `MEDIA_ROOT` to surface filesystem-only hits
(pre-v3 content the user copied in by hand).
"""

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.path_sanitize import sanitize_path_component
from arm_backend.path_template import (
    NEVER_OPTIONAL,
    TemplateValidationError,
    expand_template,
    referenced_tokens,
    required_tokens,
)
from arm_backend.slugify import slugify
from arm_common import (
    Config,
    Gpu,
    Job,
    MediaType,
    Session,
    Track,
    TrackKind,
    TrackRole,
    TranscodePreset,
)
from arm_common.encoders import EncoderSpec, get_encoder, gpu_could_serve, gpu_is_eligible
from arm_common.enums import SessionApplicationStatus, TranscodeTaskStatus, TranscodeTool
from arm_common.models import SessionApplication, TranscodeTask
from arm_common.schemas import CollisionInfo

LIVE_STATES: tuple[TranscodeTaskStatus, ...] = (
    TranscodeTaskStatus.QUEUED,
    TranscodeTaskStatus.IN_PROGRESS,
    TranscodeTaskStatus.DONE,
)


class ResolvedTask(NamedTuple):
    track_id: str
    output_path: str


def _format_duration_human(seconds: int | None) -> str:
    if seconds is None or seconds <= 0:
        return ""
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    return f"{hours:02d}h{minutes:02d}m"


def _build_track_ctx(
    job: Job,
    track: Track,
    session: Session,
    transcode_preset: TranscodePreset | None,
) -> dict[str, str]:
    """Build the per-track template context using real (not synthetic) job/track data."""
    metadata: dict[str, object] = job.metadata_json or {}
    track_index_padded = f"{track.index:02d}"

    # Music naming reads the typed `music` section (§3.4); the bare
    # top-level keys are the pre-0031 fallback.
    raw_music = metadata.get("music")
    music_meta: dict[str, Any] = raw_music if isinstance(raw_music, dict) else {}

    # Best-effort per-track music title from the music track list.
    track_title = ""
    tracks_meta = music_meta.get("tracks") or metadata.get("tracks")
    if isinstance(tracks_meta, list) and 0 <= track.index - 1 < len(tracks_meta):
        entry = tracks_meta[track.index - 1]
        if isinstance(entry, dict):
            raw_title = entry.get("title")
            if isinstance(raw_title, str):
                track_title = raw_title

    # Per-track identity overrides job-level (null = inherit). Multi-title discs
    # set these; a movie's single track leaves them null and inherits job identity.
    eff_title = track.title or job.title or ""
    eff_year = track.year if track.year is not None else job.year
    eff_season = track.season if track.season is not None else job.season
    if track.episode_number is None:
        episode = ""
    elif track.episode_number_end is not None and track.episode_number_end > track.episode_number:
        # Multi-episode title: S01E01-E02 (the Plex / Jellyfin form).
        episode = f"{track.episode_number:02d}-E{track.episode_number_end:02d}"
    else:
        episode = f"{track.episode_number:02d}"

    # Human-readable metadata fields land inside path segments; sanitise
    # so titles like "Crown / She Said" don't introduce a phantom path
    # level that ffmpeg fails to open. `track`, `transcode_slug`, and
    # `ext` are already constrained by upstream code (zero-padded int,
    # slugify(), enum).
    ctx: dict[str, str] = {
        "title": sanitize_path_component(eff_title),
        "year": str(eff_year) if eff_year is not None else "",
        "show": sanitize_path_component(job.title or ""),
        # Per-track season (set by a disc map or episode match) wins over the
        # job-level season; the metadata.get() fallback remains for pre-G-14 rows.
        # Ints are zero-padded to match the S{NN}D{NN} convention (docs/developers/architecture/02 § TV).
        "season": sanitize_path_component(
            f"{eff_season:02d}" if eff_season is not None else str(metadata.get("season") or "")
        ),
        "disc": sanitize_path_component(
            f"{job.disc_number:02d}" if job.disc_number is not None else str(metadata.get("disc") or "")
        ),
        "track": track_index_padded,
        "episode": episode,
        "episode_title": sanitize_path_component(track.episode_name or ""),
        "duration_human": _format_duration_human(track.expected_duration_seconds or track.duration_seconds),
        "artist": sanitize_path_component(str(music_meta.get("artist") or metadata.get("artist") or "")),
        "album": sanitize_path_component(str(music_meta.get("album") or metadata.get("album") or "")),
        "track_title": sanitize_path_component(track_title),
        "transcode_slug": slugify(transcode_preset.name) if transcode_preset is not None else "",
        "ext": transcode_preset.container.value if transcode_preset is not None else "",
    }
    # Session is reserved for future use (overrides_json may seed extra ctx keys);
    # keep the param so call sites don't rebreak when overrides land.
    _ = session
    return ctx


_EPISODE_TOKENS = frozenset({"episode", "episode_title"})
_WS_RUN = re.compile(r"\s+")
_DASH_RUN = re.compile(r"(?:\s*-\s*){2,}")
_DASH_BEFORE_EXT = re.compile(r"\s*-\s*(?=\.[A-Za-z0-9]+$)")
# "S01E" left behind by an empty {episode}: drop the E when no digit/letter follows.
_DANGLING_E = re.compile(r"(\bS\d+)E(?![A-Za-z0-9])")
_EXT = re.compile(r"\.[A-Za-z0-9]+$")


def _episode_tokens_required(job: Job, track: Track, session: Session) -> bool:
    """Episode tokens must resolve for episode titles (and, as before, for
    titles of unknown role on a TV disc); a bonus film or extra on a TV disc
    renders them empty instead of failing the whole apply (spec 5).

    An unidentified job (`job.media_type is None`) can still be applied to a
    TV session (`auto_session.py` allows and documents this); for a
    role-None track, fall back to the session's media type so that case
    keeps today's strict behaviour instead of silently going lenient.
    """
    if track.role is not None:
        return track.role == TrackRole.EPISODE
    return (job.media_type or session.media_type) == MediaType.TV


def _tidy_segment(seg: str) -> str:
    seg = _DANGLING_E.sub(r"\1", seg)
    seg = _WS_RUN.sub(" ", seg)
    seg = _DASH_RUN.sub(" - ", seg)
    seg = _DASH_BEFORE_EXT.sub("", seg)
    return seg.strip(" -_")


def _render_with_empty_episode(template: str, ctx: dict[str, str]) -> list[str]:
    """Render a template whose episode tokens were allowed to resolve empty
    (a bonus title on a TV disc) segment by segment. Only the `/`-segments
    that referenced an empty episode token are tidied; the rest render
    byte-for-byte."""
    segments = []
    for seg_template in template.split("/"):
        seg = expand_template(seg_template, ctx)
        if any(not ctx.get(t) for t in referenced_tokens(seg_template) & _EPISODE_TOKENS):
            seg = _tidy_segment(seg)
        segments.append(seg)
    return segments


def _with_track_suffix(name: str, track: str) -> str:
    """`Show - S01.mkv` -> `Show - S01 - T02.mkv`: keeps a disc's bonus titles
    on distinct paths when the template has no `{track}`."""
    ext = m.group(0) if (m := _EXT.search(name)) else ""
    stem = name[: len(name) - len(ext)]
    return f"{stem} - T{track}{ext}" if stem else f"T{track}{ext}"


def _track_kinds_for_media(media_type: MediaType) -> set[TrackKind]:
    if media_type in (MediaType.MOVIE, MediaType.TV):
        return {TrackKind.VIDEO_TITLE}
    if media_type == MediaType.MUSIC:
        return {TrackKind.AUDIO_TRACK}
    if media_type in (MediaType.DATA, MediaType.ISO):
        return {TrackKind.DATA_DUMP, TrackKind.VIDEO_TITLE}
    return set()  # pragma: no cover — MediaType is exhaustively handled above


def compute_outputs(
    job: Job,
    tracks: list[Track],
    session: Session,
    transcode_preset: TranscodePreset | None,
) -> list[ResolvedTask]:
    """Resolve every track's output path. Empty token → `TemplateValidationError`."""
    relevant_kinds = _track_kinds_for_media(session.media_type)
    candidates = [t for t in tracks if t.kind in relevant_kinds and not t.excluded]
    if not candidates:
        return []

    template = session.output_path_template
    referenced = referenced_tokens(template)
    required = required_tokens(template)
    resolved: list[ResolvedTask] = []
    for track in candidates:
        ctx = _build_track_ctx(job, track, session, transcode_preset)
        allowed_empty = False
        for token in sorted(required):
            if not ctx.get(token):
                if token in _EPISODE_TOKENS and not _episode_tokens_required(job, track, session):
                    allowed_empty = True
                    continue
                hint = "" if token in NEVER_OPTIONAL else f"; mark it optional as {{{token}?}} to allow that"
                raise TemplateValidationError(
                    f"track index={track.index}: token {{{token}}} resolved empty against the job's metadata{hint}"
                )
        if allowed_empty:
            segments = _render_with_empty_episode(template, ctx)
            if any(not seg for seg in segments):
                raise TemplateValidationError(
                    f"track index={track.index}: an allowed-empty episode token left an empty path segment"
                )
            if "track" not in referenced:
                segments[-1] = _with_track_suffix(segments[-1], ctx["track"])
            path = "/".join(segments)
        else:
            path = expand_template(template, ctx)
        if track.custom_filename:
            p = PurePosixPath(path)
            ext = p.suffix
            # Sanitize, then use the stem only (strip any extension the operator
            # typed) so we never produce "name.avi.mkv"; fall back to a safe stem
            # if the name sanitizes to empty (e.g. "..").
            sanitized = sanitize_path_component(track.custom_filename)
            stem = PurePosixPath(sanitized).stem or "untitled"
            name = f"{stem}{ext}" if ext else stem
            parent = str(p.parent)
            path = name if parent == "." else f"{parent}/{name}"
        resolved.append(ResolvedTask(track_id=track.id, output_path=path))
    return resolved


async def find_collisions(
    db: AsyncSession,
    paths: list[str],
    media_root: Path,
) -> list[CollisionInfo]:
    """Return any `output_path` already claimed by a live task or sitting on disk."""
    if not paths:
        return []

    stmt = (
        select(TranscodeTask.id, TranscodeTask.output_path, TranscodeTask.session_application_id)
        .where(col(TranscodeTask.output_path).in_(paths))
        .where(col(TranscodeTask.status).in_(LIVE_STATES))
    )
    result = await db.execute(stmt)
    db_hits: dict[str, str] = {}
    hit_application_ids: dict[str, str] = {}
    for row in result.all():
        if not row.output_path:
            continue
        db_hits[row.output_path] = row.id
        if row.session_application_id:
            hit_application_ids[row.output_path] = row.session_application_id

    # Batch-resolve the owning job id for every colliding task in one extra
    # query (task -> session_application -> job_id), rather than one query
    # per collision.
    application_ids = sorted(set(hit_application_ids.values()))
    job_id_by_application: dict[str, str] = {}
    if application_ids:
        app_stmt = select(SessionApplication.id, SessionApplication.job_id).where(
            col(SessionApplication.id).in_(application_ids)
        )
        app_result = await db.execute(app_stmt)
        job_id_by_application = {row.id: row.job_id for row in app_result.all()}

    collisions: list[CollisionInfo] = []
    seen: set[str] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        existing_id = db_hits.get(path)
        on_fs = (media_root / path).exists() if path else False
        if existing_id is not None:
            application_id = hit_application_ids.get(path)
            existing_job_id = job_id_by_application.get(application_id) if application_id else None
            collisions.append(
                CollisionInfo(
                    output_path=path,
                    existing_task_id=existing_id,
                    on_filesystem=False,
                    reason="existing_task",
                    existing_job_id=existing_job_id,
                )
            )
        elif on_fs:
            collisions.append(
                CollisionInfo(
                    output_path=path,
                    existing_task_id=None,
                    on_filesystem=True,
                    reason="on_disk",
                )
            )

    # Same path resolved twice in this apply — usually a template missing `{track}`
    # for a multi-track rip. Surfaces distinctly so the user can fix the template
    # rather than chase a non-existent on-disk file.
    seen_in_request: set[str] = set()
    for path in paths:
        if path in seen_in_request:
            already_flagged = any(c.output_path == path for c in collisions)
            if not already_flagged:
                collisions.append(
                    CollisionInfo(
                        output_path=path,
                        existing_task_id=None,
                        on_filesystem=False,
                        reason="duplicate_in_request",
                    )
                )
        seen_in_request.add(path)
    return collisions


def stat_exists(media_root: Path, relative: str) -> bool:
    """Stand-alone path-exists helper (importable from tests)."""
    if not relative:
        return False
    full = media_root / relative
    try:
        return full.exists()
    except OSError:
        return False


_TERMINAL_TASK_STATES: frozenset[TranscodeTaskStatus] = frozenset(
    {TranscodeTaskStatus.DONE, TranscodeTaskStatus.FAILED}
)


def is_passthrough_preset(preset: TranscodePreset | None) -> bool:
    """No preset means passthrough by definition: the transcode worker maps a
    missing preset to TranscodeTool.NONE (arm_transcode/main.py), and the
    in-process executor mirrors that."""
    return preset is None or preset.tool == TranscodeTool.NONE


async def transcode_enabled_now(db: AsyncSession) -> bool:
    """May encode work happen right now? False when the deployment is not
    transcode-capable (a ripper-only box with a stale true column must still
    refuse encode applies, or tasks would queue unrunnable forever), else
    the runtime switch (Settings > Transcoding). NULL (a row predating
    migration 0037, before the seeder's backfill) reads as enabled so
    upgrades change nothing."""
    from arm_backend.config import effective_transcode_capable, settings  # noqa: PLC0415 - avoid module cycle
    from arm_backend.seeders import CONFIG_SINGLETON_ID  # noqa: PLC0415 - avoid module cycle

    if not effective_transcode_capable(settings):
        return False
    cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    return cfg is None or cfg.transcode_enabled is not False


async def encoder_available(db: AsyncSession, encoder_id: str) -> bool:
    """May an apply proceed with this preset's catalog encoder right now?

    An id no longer in the catalog (a stale row from a removed encoder) is
    treated as unavailable rather than raising, matching how the dispatcher's
    GPU claim degrades: `preset`/`cpu`/`any` never depend on hardware (an
    `any_<codec>` encoder falls back to the CPU at dispatch time when
    nothing eligible shows up, `TranscodeDispatcher._claim_gpu_for_task`),
    so those are never refused here. A vendor-pinned `gpu` encoder needs a
    device per `gpu_encoder_state`; dispatch would otherwise fail the task
    once it reached the front of the queue, so apply-time refuses it up
    front instead.
    """
    try:
        spec = get_encoder(encoder_id)
    except ValueError:
        return False
    if spec.kind != "gpu":
        return True
    all_gpus = (await db.execute(select(Gpu))).scalars().all()
    return gpu_encoder_state(spec, all_gpus) != "unavailable"


GpuEncoderState = Literal["verified", "awaiting_probe", "unavailable"]


def gpu_encoder_state(spec: EncoderSpec, gpus: Sequence[Gpu]) -> GpuEncoderState:
    """Can the inventory serve this `gpu` or `any` encoder on a GPU?

    `verified`: an enabled row whose probe verified the codec
    (`gpu_is_eligible`), of the encoder's vendor for a vendor-pinned one.
    `awaiting_probe`: none yet, but a never-probed row that could serve it
    (`gpu_could_serve`) has its probe reserved or running
    (`gpu_awaiting_probe`), so a task queues until the probe decides, exactly
    as the claim does. Shared by the apply gate and GET /api/encoders so the
    two never disagree.
    """
    from arm_backend.transcode_dispatcher import gpu_awaiting_probe  # noqa: PLC0415 - avoid module cycle

    codec = str(spec.codec)
    if any(gpu_is_eligible(g, codec) and (spec.kind == "any" or g.vendor == spec.vendor) for g in gpus):
        return "verified"
    if any(gpu_could_serve(g, spec) and gpu_awaiting_probe(g) for g in gpus):
        return "awaiting_probe"
    return "unavailable"


class AggregateOutcome(NamedTuple):
    """Result of `_aggregate_application`. `transitioned_to` is None when the
    application is still RUNNING (some tasks remain non-terminal); otherwise
    one of DONE / DONE_PARTIAL / FAILED.
    """

    transitioned_to: SessionApplicationStatus | None
    event_type: str | None  # "session.completed" / "session.partial" / "session.failed"


async def aggregate_session_application(
    db: AsyncSession,
    application: SessionApplication,
) -> AggregateOutcome:
    """Recompute the session application's status from its tasks.

    Called from the transcoder router on every task complete/fail. Mutates
    `application` in place when transitioning to a terminal state and stamps
    `completed_at`. Caller is responsible for committing.
    """
    rows = (
        (await db.execute(select(TranscodeTask).where(col(TranscodeTask.session_application_id) == application.id)))
        .scalars()
        .all()
    )
    statuses = [r.status for r in rows]
    if not statuses:
        # Defensive: no tasks fanned out (waiting_identify path) — keep status untouched.
        return AggregateOutcome(transitioned_to=None, event_type=None)

    if any(s not in _TERMINAL_TASK_STATES for s in statuses):
        return AggregateOutcome(transitioned_to=None, event_type=None)

    done_count = sum(1 for s in statuses if s == TranscodeTaskStatus.DONE)
    if done_count == len(statuses):
        target = SessionApplicationStatus.DONE
        event = "session.completed"
    elif done_count == 0:
        target = SessionApplicationStatus.FAILED
        event = "session.failed"
    else:
        target = SessionApplicationStatus.DONE_PARTIAL
        event = "session.partial"

    if application.status == target:
        # Idempotent re-run after a retry — don't re-emit.
        return AggregateOutcome(transitioned_to=None, event_type=None)

    application.status = target
    application.completed_at = datetime.now(UTC)
    return AggregateOutcome(transitioned_to=target, event_type=event)
