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
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend import job_events
from arm_backend.constants import CONFIG_SINGLETON_ID
from arm_backend.path_sanitize import sanitize_path_component
from arm_backend.path_template import (
    NEVER_OPTIONAL,
    TemplateValidationError,
    expand_template,
    optional_tokens,
    referenced_tokens,
    required_tokens,
)
from arm_backend.identity.ids import current_ids
from arm_backend.session_routing import routing_media_type
from arm_backend.slugify import slugify
from arm_backend.log_safely import log_safely
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
from arm_common.schemas import CollisionInfo, MusicTags

if TYPE_CHECKING:
    from arm_backend.ws.hub import WSHub

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


def _music_meta(metadata: dict[str, object]) -> dict[str, Any]:
    """The job's typed `music` section, or {} when absent or malformed."""
    raw_music = metadata.get("music")
    return raw_music if isinstance(raw_music, dict) else {}


def _music_tracks(music_meta: dict[str, Any], metadata: dict[str, object]) -> list[Any]:
    """The music track listing; the bare top-level `tracks` key is the fallback for older rows."""
    tracks_meta = music_meta.get("tracks") or metadata.get("tracks")
    return tracks_meta if isinstance(tracks_meta, list) else []


def _music_track_entry(music_meta: dict[str, Any], metadata: dict[str, object], index: int) -> dict[str, Any]:
    """The listing entry for the 1-based track index, or {} when there is none."""
    tracks_meta = _music_tracks(music_meta, metadata)
    if 0 <= index - 1 < len(tracks_meta):
        entry = tracks_meta[index - 1]
        if isinstance(entry, dict):
            return entry
    return {}


def _music_track_title(music_meta: dict[str, Any], metadata: dict[str, object], index: int) -> str:
    """Return the best-effort music title for the 1-based track index, or ''."""
    raw_title = _music_track_entry(music_meta, metadata, index).get("title")
    return raw_title if isinstance(raw_title, str) else ""


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def music_tags_for(job: Job, track: Track) -> MusicTags | None:
    """The tags `track`'s encoded file carries, or None for a job that is not music.

    Read from the same stored identity the output filename uses, and resolved
    the same way: the 1-based track index into the music track listing.
    Unknown fields stay None so the transcoder leaves them out of the file.
    """
    if routing_media_type(job) != MediaType.MUSIC:
        return None
    metadata: dict[str, object] = job.metadata_json or {}
    music_meta = _music_meta(metadata)
    entry = _music_track_entry(music_meta, metadata, track.index)
    track_total = len(_music_tracks(music_meta, metadata))
    return MusicTags(
        artist=_str_or_none(music_meta.get("artist") or metadata.get("artist")),
        album=_str_or_none(music_meta.get("album") or metadata.get("album")),
        title=_str_or_none(entry.get("title")),
        year=job.year,
        disc_number=job.disc_number if job.disc_number is not None else _int_or_none(entry.get("disc_number")),
        track_number=track.index,
        track_total=track_total or None,
        musicbrainz_release_id=current_ids(job).musicbrainz_release,
    )


def _effective_identity(job: Job, track: Track) -> tuple[str, int | None, int | None]:
    """Return the track's effective (title, year, season), falling back to the job's."""
    # Per-track identity overrides job-level (null = inherit). Multi-title discs
    # set these; a movie's single track leaves them null and inherits job identity.
    # A track with its own title is its own identity: its year is its own too
    # (none when unset), never the disc's.
    eff_title = track.title or job.title or ""
    eff_year = track.year if track.title else job.year
    eff_season = track.season if track.season is not None else job.season
    return eff_title, eff_year, eff_season


def _episode_label(track: Track) -> str:
    """Return the zero-padded episode label, with an end range when the title spans episodes."""
    if track.episode_number is None:
        return ""
    if track.episode_number_end is not None and track.episode_number_end > track.episode_number:
        # Multi-episode title: S01E01-E02 (the Plex / Jellyfin form).
        return f"{track.episode_number:02d}-E{track.episode_number_end:02d}"
    return f"{track.episode_number:02d}"


def _track_number(track: Track) -> int:
    """The track's number in a file name: video titles count from 1, other kinds keep their index."""
    return track.index + 1 if track.kind == TrackKind.VIDEO_TITLE else track.index


def _track_label(track: Track, number: int) -> str:
    """`Track NN` for a track with no title of its own, empty for a track that names itself."""
    return "" if track.title else f"Track {number:02d}"


def _build_track_ctx(
    job: Job,
    track: Track,
    transcode_preset: TranscodePreset | None,
) -> dict[str, str]:
    """Build the per-track template context using real (not synthetic) job/track data."""
    metadata: dict[str, object] = job.metadata_json or {}
    track_number = _track_number(track)

    # Music naming reads the typed `music` section; the bare
    # top-level keys are the fallback for older rows.
    music_meta = _music_meta(metadata)

    track_title = _music_track_title(music_meta, metadata, track.index)
    if track.kind == TrackKind.AUDIO_TRACK and not track_title.strip():
        # A CD may be identified with tracks left untitled: name them by
        # number, padded like {track}, so a required {track_title} renders.
        track_title = f"Track {track_number:02d}"

    eff_title, eff_year, eff_season = _effective_identity(job, track)
    episode = _episode_label(track)

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
        # job-level season; the metadata.get() fallback remains for rows without a per-track season.
        # Ints are zero-padded to match the S{NN}D{NN} convention (docs/developers/architecture/02 § TV).
        "season": sanitize_path_component(
            f"{eff_season:02d}" if eff_season is not None else str(metadata.get("season") or "")
        ),
        "disc": sanitize_path_component(
            f"{job.disc_number:02d}" if job.disc_number is not None else str(metadata.get("disc") or "")
        ),
        "track": f"{track_number:02d}",
        "track_label": _track_label(track, track_number),
        "edition": sanitize_path_component(track.edition or ""),
        "episode": episode,
        "episode_title": sanitize_path_component(track.episode_name or ""),
        "duration_human": _format_duration_human(track.expected_duration_seconds or track.duration_seconds),
        "artist": sanitize_path_component(str(music_meta.get("artist") or metadata.get("artist") or "")),
        "album": sanitize_path_component(str(music_meta.get("album") or metadata.get("album") or "")),
        "track_title": sanitize_path_component(track_title),
        "transcode_slug": slugify(transcode_preset.name) if transcode_preset is not None else "",
        "ext": transcode_preset.container.value if transcode_preset is not None else "",
    }
    return ctx


_EPISODE_TOKENS = frozenset({"episode", "episode_title"})
_WS_RUN = re.compile(r"\s+")
_DASH_RUN = re.compile(r"(?:\s*-\s*){2,}")
_DASH_BEFORE_EXT = re.compile(r"\s*-\s*(?=\.[A-Za-z0-9]+$)")
# "S01E" left behind by an empty {episode}: drop the E when no digit/letter follows.
_DANGLING_E = re.compile(r"(\bS\d+)E(?![A-Za-z0-9])")
_EXT = re.compile(r"\.[A-Za-z0-9]+$")


def _episode_tokens_required(job: Job, track: Track, session: Session) -> bool:
    """Episode tokens must resolve for episode titles (and for
    titles of unknown role on a TV disc); a bonus film or extra on a TV disc
    renders them empty instead of failing the whole apply.

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
    byte-for-byte. A segment left empty only by dropped optional tokens
    (`{year?}`) collapses away, as it does in a whole-template render."""
    segments = []
    for seg_template in template.split("/"):
        seg = expand_template(seg_template, ctx, allow_empty=True)
        if any(not ctx.get(t) for t in referenced_tokens(seg_template) & _EPISODE_TOKENS):
            seg = _tidy_segment(seg)
        elif not seg and optional_tokens(seg_template):
            continue
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
        return {TrackKind.DATA_DUMP, TrackKind.DISC_BACKUP, TrackKind.VIDEO_TITLE}
    return set()  # pragma: no cover — MediaType is exhaustively handled above


def _check_required_tokens(job: Job, track: Track, session: Session, ctx: dict[str, str], required: set[str]) -> bool:
    """Raise when a required token resolved empty; return True when only episode
    tokens did and this track may leave them empty."""
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
    return allowed_empty


def _render_with_empty_episode_path(template: str, ctx: dict[str, str], referenced: set[str], track_index: int) -> str:
    """Render the path segment by segment for a track whose episode tokens may stay empty."""
    segments = _render_with_empty_episode(template, ctx)
    if any(not seg for seg in segments):
        raise TemplateValidationError(
            f"track index={track_index}: an allowed-empty episode token left an empty path segment"
        )
    if "track" not in referenced:
        segments[-1] = _with_track_suffix(segments[-1], ctx["track"])
    return "/".join(segments)


def _apply_custom_filename(path: str, custom_filename: str) -> str:
    """Replace the path's file stem with the sanitised custom filename, keeping its extension."""
    p = PurePosixPath(path)
    ext = p.suffix
    # Sanitize, then use the stem only (strip any extension the operator
    # typed) so we never produce "name.avi.mkv"; fall back to a safe stem
    # if the name sanitizes to empty (e.g. "..").
    sanitized = sanitize_path_component(custom_filename)
    stem = PurePosixPath(sanitized).stem or "untitled"
    name = f"{stem}{ext}" if ext else stem
    parent = str(p.parent)
    return name if parent == "." else f"{parent}/{name}"


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
        ctx = _build_track_ctx(job, track, transcode_preset)
        if _check_required_tokens(job, track, session, ctx, required):
            path = _render_with_empty_episode_path(template, ctx, referenced, track.index)
        else:
            path = expand_template(template, ctx)
        if track.custom_filename:
            path = _apply_custom_filename(path, track.custom_filename)
        resolved.append(ResolvedTask(track_id=track.id, output_path=path))
    return resolved


async def _live_task_hits(db: AsyncSession, paths: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    """Return the live tasks holding `paths` as (task id, application id) maps keyed by path."""
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
    return db_hits, hit_application_ids


async def _job_ids_by_application(db: AsyncSession, application_ids: list[str]) -> dict[str, str]:
    """Map each session application id to its owning job id."""
    # Batch-resolve the owning job id for every colliding task in one extra
    # query (task -> session_application -> job_id), rather than one query
    # per collision.
    job_id_by_application: dict[str, str] = {}
    if application_ids:
        app_stmt = select(SessionApplication.id, SessionApplication.job_id).where(
            col(SessionApplication.id).in_(application_ids)
        )
        app_result = await db.execute(app_stmt)
        job_id_by_application = {row.id: row.job_id for row in app_result.all()}
    return job_id_by_application


def _collisions_for_paths(
    paths: list[str],
    db_hits: dict[str, str],
    hit_application_ids: dict[str, str],
    job_id_by_application: dict[str, str],
    media_root: Path,
) -> list[CollisionInfo]:
    """Flag each distinct path held by a live task or already on disk."""
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
    return collisions


def _add_duplicate_collisions(paths: list[str], collisions: list[CollisionInfo]) -> None:
    """Append a collision for each path repeated in the request and not already flagged."""
    flagged_paths = {c.output_path for c in collisions}
    seen_in_request: set[str] = set()
    for path in paths:
        if path in seen_in_request:
            if path not in flagged_paths:
                flagged_paths.add(path)
                collisions.append(
                    CollisionInfo(
                        output_path=path,
                        existing_task_id=None,
                        on_filesystem=False,
                        reason="duplicate_in_request",
                    )
                )
        seen_in_request.add(path)


async def find_collisions(
    db: AsyncSession,
    paths: list[str],
    media_root: Path,
) -> list[CollisionInfo]:
    """Return any `output_path` already claimed by a live task or sitting on disk."""
    if not paths:
        return []

    db_hits, hit_application_ids = await _live_task_hits(db, paths)
    application_ids = sorted(set(hit_application_ids.values()))
    job_id_by_application = await _job_ids_by_application(db, application_ids)
    collisions = _collisions_for_paths(paths, db_hits, hit_application_ids, job_id_by_application, media_root)

    # Same path resolved twice in this apply — usually a template missing `{track}`
    # for a multi-track rip. Surfaces distinctly so the user can fix the template
    # rather than chase a non-existent on-disk file.
    _add_duplicate_collisions(paths, collisions)
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
    done: int = 0  # task counts once the application settled; 0 while it has not
    failed: int = 0
    total: int = 0


# Settled by `aggregate_session_application` once every task finished; a
# re-queued failed task puts the application back in flight.
_REOPENABLE_APPLICATION_STATUSES: frozenset[SessionApplicationStatus] = frozenset(
    {SessionApplicationStatus.FAILED, SessionApplicationStatus.DONE_PARTIAL, SessionApplicationStatus.DONE}
)


def reopen_session_application(application: SessionApplication) -> bool:
    """Put a settled application back to RUNNING (completed_at cleared) after
    one of its failed tasks was re-queued, so the job reads as transcoding
    again and the aggregate settles it afresh when the retry finishes.
    Returns whether it changed; an application still in flight is left as is.
    The caller commits."""
    if application.status not in _REOPENABLE_APPLICATION_STATUSES:
        return False
    application.status = SessionApplicationStatus.RUNNING
    application.completed_at = None
    return True


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
    return AggregateOutcome(
        transitioned_to=target,
        event_type=event,
        done=done_count,
        failed=len(statuses) - done_count,
        total=len(statuses),
    )


async def emit_session_outcome(
    hub: "WSHub", db: AsyncSession, application: SessionApplication, event_type: str
) -> None:
    """Announce a session application's `session.*` event on `transcode.events`."""
    await hub.emit(
        topic="transcode.events",
        event_type=event_type,
        payload={
            "session_application_id": application.id,
            "session_id": application.session_id,
            "job_id": application.job_id,
            "status": application.status.value,
        },
        job_id=application.job_id,
        session=db,
    )


async def emit_task_failed(hub: "WSHub", db: AsyncSession, task: TranscodeTask) -> None:
    """Announce a task's `task.failed` event on `transcode.events`."""
    application = (
        await db.execute(select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id))
    ).scalar_one()
    await hub.emit(
        topic="transcode.events",
        event_type="task.failed",
        payload={
            "task_id": task.id,
            "session_application_id": task.session_application_id,
            "last_error": task.last_error,
        },
        job_id=application.job_id,
        track_id=task.source_track_id,
        session=db,
    )


async def settle_session_application(
    db: AsyncSession, hub: "WSHub", application: SessionApplication
) -> AggregateOutcome:
    """Recompute the application's status from its tasks and announce a terminal
    transition. The caller commits, logs its task's own milestone, then passes the
    outcome to `log_session_settled`."""
    outcome = await aggregate_session_application(db, application)
    if outcome.event_type is not None:
        await emit_session_outcome(hub, db, application, outcome.event_type)
    return outcome


async def log_session_settled(db: AsyncSession, application: SessionApplication, outcome: AggregateOutcome) -> None:
    """Log `session.completed` for a committed terminal transition; nothing when the
    application did not settle. A failure in the logging is logged, never raised."""
    if outcome.event_type is not None:
        await log_safely("session.completed", _log_session_settled(db, application, outcome))


async def _log_session_settled(db: AsyncSession, application: SessionApplication, outcome: AggregateOutcome) -> None:
    """Log `session.completed` with the settled application's task counts."""
    job = (await db.execute(select(Job).where(col(Job.id) == application.job_id))).scalar_one_or_none()
    if job is None:
        return
    job_events.log_session_completed(
        job, outcome.done, outcome.failed, outcome.total, session_application_id=application.id
    )
