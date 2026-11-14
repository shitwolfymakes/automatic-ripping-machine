"""Builds the job list and detail views, with their progress summaries and the batched lookups behind them."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.config import settings
from arm_common import (
    DiscFingerprint,
    Job,
    JobStatus,
    SessionApplication,
    SessionApplicationStatus,
    Track,
    TrackStatus,
    TranscodeTaskStatus,
)
from arm_common.enums import TERMINAL_JOB_STATUSES
from arm_common.models import TranscodeTask
from arm_common.schemas import (
    DiscFingerprintView,
    JobDetailView,
    JobView,
    PreviousRipView,
    RipProgressSummary,
    TrackView,
    TranscodeProgressSummary,
)
from arm_common.schemas.job_metadata import previously_ripped_job_id


def _summarize_rip_progress(tracks: list[Track]) -> RipProgressSummary:
    """Aggregate `tracks` (one job's worth) into a `RipProgressSummary`.

    `current_track_index` is the 1-based ordinal among tracks sorted by
    `Track.index` of the row in `IN_PROGRESS`. The dispatcher transitions
    one track at a time, so at most one is `IN_PROGRESS` per job; if more
    than one ever appeared (e.g. mid-rewrite of the dispatcher) we'd pick
    the lowest-index one as a sane default.
    """
    sorted_tracks = sorted(tracks, key=lambda t: t.index)
    done = sum(1 for t in sorted_tracks if t.status == TrackStatus.DONE)
    failed = sum(1 for t in sorted_tracks if t.status == TrackStatus.FAILED)
    current_track_id: str | None = None
    current_track_index: int | None = None
    for ordinal, t in enumerate(sorted_tracks, start=1):
        if t.status == TrackStatus.IN_PROGRESS:
            current_track_id = t.id
            current_track_index = ordinal
            break
    return RipProgressSummary(
        tracks_total=len(sorted_tracks),
        tracks_done=done,
        tracks_failed=failed,
        current_track_id=current_track_id,
        current_track_index=current_track_index,
    )


# A session_application counts as "terminal" for the job-done rollup when its
# own status is terminal, OR it fanned out 0 tasks and isn't genuinely waiting
# to be identified (the rip-only / all-excluded 0-task QUEUED deadlock — see
# the design doc; absorbed here in the read layer).
_TERMINAL_SESSION_STATUSES: frozenset[SessionApplicationStatus] = frozenset(
    {
        SessionApplicationStatus.DONE,
        SessionApplicationStatus.DONE_PARTIAL,
        SessionApplicationStatus.FAILED,
        SessionApplicationStatus.CANCELLED,
    }
)


def _session_app_is_terminal(sa: SessionApplicationStatus, task_count: int) -> bool:
    if sa in _TERMINAL_SESSION_STATUSES:
        return True
    return task_count == 0 and sa != SessionApplicationStatus.WAITING_IDENTIFY


def _parked_session_ids(sas: list[SessionApplication]) -> list[str]:
    parked = [sa for sa in sas if sa.status == SessionApplicationStatus.WAITING_IDENTIFY]
    # created_at is server-defaulted, so it can be None on unflushed/fake rows;
    # ULID ids break ties and order those rows by creation too.
    parked.sort(key=lambda sa: (sa.created_at is None, sa.created_at or datetime.min.replace(tzinfo=UTC), sa.id))
    return [sa.session_id for sa in parked]


def _parked_apps_are_settled(job: Job) -> bool:
    """Is a parked application with no tasks no longer in flight? True once
    the rip is over: rip-complete drained what it could on a ripped job, and
    a failed or abandoned job never drains. A RIPPED_AWAITING_IDENTIFY job's
    (or an unidentified RIPPED_PARTIAL one's) parked application is still
    waiting for resolve to drain it, but it is waiting on identity, not
    transcoding, so it is settled for the rollup too;
    `parked_session_ids` shows it as waiting."""
    return job.status in TERMINAL_JOB_STATUSES


def _summarize_transcode_progress(
    session_apps: list[SessionApplication],
    tasks: list[TranscodeTask],
    *,
    parked_settled: bool = False,
) -> TranscodeProgressSummary | None:
    """Roll a job's session_applications (+ their tasks) into one job-level
    transcode state. Returns None when no session has been applied.

    Aggregates ALL applications, not the latest: a job can hold a DONE app
    plus a newer QUEUED app (non-colliding outputs), and is "transcoding"
    until every application is terminal.

    `parked_settled` (see `_parked_apps_are_settled`): a WAITING_IDENTIFY
    application with no tasks is then not in flight, only parked (its reason
    is shown through `parked_session_ids`), so it is left out of the rollup;
    otherwise a ripped job would read "Transcoding 0/0" forever.
    """
    tasks_by_app: dict[str, list[TranscodeTask]] = {}
    for t in tasks:
        tasks_by_app.setdefault(t.session_application_id, []).append(t)

    if parked_settled:
        session_apps = [
            sa
            for sa in session_apps
            if not (sa.status == SessionApplicationStatus.WAITING_IDENTIFY and not tasks_by_app.get(sa.id))
        ]
    if not session_apps:
        return None

    all_terminal = all(_session_app_is_terminal(sa.status, len(tasks_by_app.get(sa.id, []))) for sa in session_apps)

    tasks_total = len(tasks)
    tasks_done = sum(1 for t in tasks if t.status == TranscodeTaskStatus.DONE)
    tasks_failed = sum(1 for t in tasks if t.status == TranscodeTaskStatus.FAILED)
    percent = (sum(t.progress_pct for t in tasks) / tasks_total) if tasks_total else 100.0

    state: Literal["transcoding", "done", "done_partial", "failed"]
    if not all_terminal:
        state = "transcoding"
    elif tasks_failed and tasks_done:
        state = "done_partial"
    elif tasks_failed and not tasks_done:
        state = "failed"
    else:
        # all terminal, no failures (incl. the 0-task absorbed case)
        state = "done"

    return TranscodeProgressSummary(
        state=state,
        tasks_total=tasks_total,
        tasks_done=tasks_done,
        tasks_failed=tasks_failed,
        percent=round(percent, 1),
    )


async def _tracks_for_ripping(session: AsyncSession, jobs: list[Job]) -> dict[str, list[Track]]:
    """The tracks of the ripping jobs in the page, grouped by job id."""
    # One batched track lookup keyed on the ripping-job IDs feeds the
    # dashboard's "Track N of M" line without an N+1 fetch. Skipped
    # entirely when no job in the page is ripping (which is the common
    # case on the recent-jobs slice).
    ripping_ids = [j.id for j in jobs if j.status == JobStatus.RIPPING]
    tracks_by_job: dict[str, list[Track]] = {}
    if ripping_ids:
        track_rows = (
            (
                await session.execute(
                    select(Track)
                    .where(col(Track.job_id).in_(ripping_ids))
                    .order_by(col(Track.job_id), col(Track.index))
                )
            )
            .scalars()
            .all()
        )
        for tr in track_rows:
            tracks_by_job.setdefault(tr.job_id, []).append(tr)
    return tracks_by_job


async def _apps_and_tasks_for(
    session: AsyncSession, job_ids: list[str]
) -> tuple[dict[str, list[SessionApplication]], dict[str, list[TranscodeTask]]]:
    """The session applications and transcode tasks of the given jobs, grouped by job id."""
    # Batched session_application + transcode_task lookup keyed on ALL job ids
    # in the page (any job can have a session, not just ripping jobs).
    sas_by_job: dict[str, list[SessionApplication]] = {}
    transcode_tasks_by_job: dict[str, list[TranscodeTask]] = {}
    if job_ids:
        sa_rows = (
            (await session.execute(select(SessionApplication).where(col(SessionApplication.job_id).in_(job_ids))))
            .scalars()
            .all()
        )
        sa_id_to_job: dict[str, str] = {}
        for sa in sa_rows:
            sas_by_job.setdefault(sa.job_id, []).append(sa)
            sa_id_to_job[sa.id] = sa.job_id
        if sa_id_to_job:
            task_rows = (
                (
                    await session.execute(
                        select(TranscodeTask).where(
                            col(TranscodeTask.session_application_id).in_(list(sa_id_to_job.keys()))
                        )
                    )
                )
                .scalars()
                .all()
            )
            for t in task_rows:
                # The task query filters on sa_id_to_job's keys, so every
                # returned task's session_application_id is in the map.
                owning_job = sa_id_to_job[t.session_application_id]
                transcode_tasks_by_job.setdefault(owning_job, []).append(t)
    return sas_by_job, transcode_tasks_by_job


async def job_list_views(session: AsyncSession, jobs: list[Job]) -> list[JobView]:
    """The JobView of each job, with its rip and transcode progress filled in."""
    tracks_by_job = await _tracks_for_ripping(session, jobs)
    job_ids = [j.id for j in jobs]
    sas_by_job, transcode_tasks_by_job = await _apps_and_tasks_for(session, job_ids)

    views: list[JobView] = []
    for j in jobs:
        view = JobView.model_validate(j)
        if j.status == JobStatus.RIPPING:
            view.rip_progress = _summarize_rip_progress(tracks_by_job.get(j.id, []))
        view.transcode_progress = _summarize_transcode_progress(
            sas_by_job.get(j.id, []), transcode_tasks_by_job.get(j.id, []), parked_settled=_parked_apps_are_settled(j)
        )
        view.parked_session_ids = _parked_session_ids(sas_by_job.get(j.id, []))
        views.append(view)
    return views


def _latest_task_by_track(tasks: list[TranscodeTask]) -> dict[str, TranscodeTask]:
    """The most recent transcode task of each source track."""
    # Most-recent transcode task per source track (ULID ids are monotonic,
    # so the greatest id is the newest task). Built from the already-loaded
    # job_tasks — no extra query.
    latest_task: dict[str, TranscodeTask] = {}
    for task in tasks:
        prev = latest_task.get(task.source_track_id)
        if prev is None or task.id > prev.id:
            latest_task[task.source_track_id] = task
    return latest_task


def _track_view(track: Track, latest_task: dict[str, TranscodeTask]) -> TrackView:
    """The TrackView of a track, with the status and frame rate of its latest transcode task."""
    tv = TrackView.model_validate(track)
    task = latest_task.get(track.id)
    if task is not None:
        tv.transcode_status = task.status
        tv.transcode_fps = task.fps
        tv.transcode_avg_fps = task.avg_fps
    return tv


async def job_detail_view(session: AsyncSession, job: Job) -> JobDetailView:
    """The job with its tracks, fingerprints, transcode progress and earlier rip."""
    tracks = (
        (await session.execute(select(Track).where(col(Track.job_id) == job.id).order_by(col(Track.index))))
        .scalars()
        .all()
    )
    fingerprints = (
        (
            await session.execute(
                select(DiscFingerprint).where(col(DiscFingerprint.job_id) == job.id).order_by(col(DiscFingerprint.algo))
            )
        )
        .scalars()
        .all()
    )
    sas_by_job, tasks_by_job = await _apps_and_tasks_for(session, [job.id])
    sas = sas_by_job.get(job.id, [])
    job_tasks = tasks_by_job.get(job.id, [])
    job_view = JobView.model_validate(job)
    job_view.transcode_progress = _summarize_transcode_progress(
        sas, job_tasks, parked_settled=_parked_apps_are_settled(job)
    )
    job_view.parked_session_ids = _parked_session_ids(sas)
    latest_task = _latest_task_by_track(job_tasks)
    return JobDetailView(
        job=job_view,
        tracks=[_track_view(t, latest_task) for t in tracks],
        fingerprints=[DiscFingerprintView.model_validate(fp) for fp in fingerprints],
        previous_rip=await _previous_rip_view(session, job),
    )


async def _previous_rip_view(db: AsyncSession, job: Job) -> PreviousRipView | None:
    """The earlier rip a previously-ripped hold names, with whether its
    finished outputs are still on disk. None when there is none or it has
    since been deleted."""
    previous_id = previously_ripped_job_id(job.metadata_json)
    if previous_id is None:
        return None
    previous = (await db.execute(select(Job).where(col(Job.id) == previous_id))).scalar_one_or_none()
    if previous is None:
        return None
    # Two single-table reads rather than _resolve_media_outputs' join, so the
    # detail endpoint stays FakeSession-compatible.
    track_ids = [
        t.id for t in (await db.execute(select(Track).where(col(Track.job_id) == previous.id))).scalars().all()
    ]
    outputs: list[Path] = []
    if track_ids:
        media_root = Path(settings.MEDIA_ROOT)
        done = (
            (
                await db.execute(
                    select(TranscodeTask)
                    .where(col(TranscodeTask.source_track_id).in_(track_ids))
                    .where(col(TranscodeTask.status) == TranscodeTaskStatus.DONE)
                )
            )
            .scalars()
            .all()
        )
        outputs = [media_root / t.output_path for t in done if t.output_path]
    return PreviousRipView(
        job_id=previous.id,
        title=previous.title,
        year=previous.year,
        status=previous.status,
        ripped_at=previous.ripped_at,
        outputs_present=all(p.exists() for p in outputs) if outputs else None,
    )
