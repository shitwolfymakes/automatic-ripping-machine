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

from pathlib import Path
from typing import NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.path_template import TemplateValidationError, expand_template, referenced_tokens
from arm_backend.slugify import slugify
from arm_common import (
    Job,
    MediaType,
    Session,
    Track,
    TrackKind,
    TranscodePreset,
)
from arm_common.enums import TranscodeTaskStatus
from arm_common.models import TranscodeTask
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

    # Best-effort per-track music title: job.metadata_json["tracks"] is populated
    # by the music identification flow (separate phase); we read it if present.
    track_title = ""
    tracks_meta = metadata.get("tracks")
    if isinstance(tracks_meta, list) and 0 <= track.index - 1 < len(tracks_meta):
        entry = tracks_meta[track.index - 1]
        if isinstance(entry, dict):
            raw_title = entry.get("title")
            if isinstance(raw_title, str):
                track_title = raw_title

    ctx: dict[str, str] = {
        "title": job.title or "",
        "year": str(job.year) if job.year is not None else "",
        "show": job.title or "",
        "season": str(metadata.get("season") or ""),
        "disc": str(metadata.get("disc") or ""),
        "track": track_index_padded,
        "duration_human": _format_duration_human(track.expected_duration_seconds or track.duration_seconds),
        "artist": str(metadata.get("artist") or ""),
        "album": str(metadata.get("album") or ""),
        "track_title": track_title,
        "transcode_slug": slugify(transcode_preset.name) if transcode_preset is not None else "",
        "ext": transcode_preset.container.value if transcode_preset is not None else "",
    }
    # Session is reserved for future use (overrides_json may seed extra ctx keys);
    # keep the param so call sites don't rebreak when overrides land.
    _ = session
    return ctx


def _track_kinds_for_media(media_type: MediaType) -> set[TrackKind]:
    if media_type in (MediaType.MOVIE, MediaType.TV):
        return {TrackKind.VIDEO_TITLE}
    if media_type == MediaType.MUSIC:
        return {TrackKind.AUDIO_TRACK}
    if media_type in (MediaType.DATA, MediaType.ISO):
        return {TrackKind.DATA_DUMP, TrackKind.VIDEO_TITLE}
    return set()


def compute_outputs(
    job: Job,
    tracks: list[Track],
    session: Session,
    transcode_preset: TranscodePreset | None,
) -> list[ResolvedTask]:
    """Resolve every track's output path. Empty token → `TemplateValidationError`."""
    relevant_kinds = _track_kinds_for_media(session.media_type)
    candidates = [t for t in tracks if t.kind in relevant_kinds]
    if not candidates:
        return []

    template = session.output_path_template
    referenced = referenced_tokens(template)
    resolved: list[ResolvedTask] = []
    for track in candidates:
        ctx = _build_track_ctx(job, track, session, transcode_preset)
        for token in referenced:
            if not ctx.get(token):
                raise TemplateValidationError(
                    f"track index={track.index}: token {{{token}}} resolved empty against the job's metadata"
                )
        path = expand_template(template, ctx)
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
        select(TranscodeTask.id, TranscodeTask.output_path)
        .where(col(TranscodeTask.output_path).in_(paths))
        .where(col(TranscodeTask.status).in_(LIVE_STATES))
    )
    result = await db.execute(stmt)
    db_hits: dict[str, str] = {row.output_path: row.id for row in result.all() if row.output_path}

    collisions: list[CollisionInfo] = []
    seen: set[str] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        existing_id = db_hits.get(path)
        on_fs = (media_root / path).exists() if path else False
        if existing_id is not None or on_fs:
            collisions.append(
                CollisionInfo(
                    output_path=path,
                    existing_task_id=existing_id,
                    on_filesystem=on_fs and existing_id is None,
                )
            )

    # Cross-session collision *within this apply*: same path appears twice.
    seen_in_request: set[str] = set()
    for path in paths:
        if path in seen_in_request:
            already_flagged = any(c.output_path == path for c in collisions)
            if not already_flagged:
                collisions.append(CollisionInfo(output_path=path, existing_task_id=None, on_filesystem=False))
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
