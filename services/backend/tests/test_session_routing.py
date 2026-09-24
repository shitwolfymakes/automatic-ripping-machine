"""G-01 (gap analysis §5.1): session ROUTING is separate from auto-apply
PERMISSION.

`resolve_routed_session_id` answers "which session is routed to this job"
(explicit per-rip choice, else the drive default) with NO
auto_transcode_on_idle gating — it shapes the rip and the naming preview.
`auto_apply_allowed` answers "may rip-complete queue it unattended" — the
flag, bypassed by an explicit per-rip choice.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend.auto_session import auto_apply_allowed, resolve_routed_session_id  # noqa: E402
from arm_common import (  # noqa: E402
    Config,
    DiscType,
    Drive,
    DriveStatus,
    Job,
    JobStatus,
    MediaType,
    Session,
    SessionRoute,
)

from tests._fakes import FakeSession  # noqa: E402


def _job(
    pending: str | None = None,
    *,
    media_type: MediaType | None = None,
    disc_type: DiscType = DiscType.DVD,
) -> Job:
    return Job(
        id="job_01JZXR7K3M5Q8N4VWA00000001",
        drive_id="drv_x",
        disc_type=disc_type,
        media_type=media_type,
        status=JobStatus.RIPPED,
        metadata_json={},
        pending_session_id=pending,
    )


def _seed(
    db: FakeSession,
    *,
    default_session_id: str | None,
    flag: bool,
    routes: list[SessionRoute] | None = None,
    sessions: list[Session] | None = None,
) -> None:
    db.rows["drives"] = [
        Drive(
            id="drv_x",
            hostname="h",
            device_path="/dev/sr0",
            status=DriveStatus.ONLINE,
            default_session_id=default_session_id,
        )
    ]
    db.rows["config"] = [Config(id=1, auto_transcode_on_idle=flag, auto_rip_on_insert=True, block_on_miss=True)]
    db.rows["session_routes"] = routes or []
    db.rows["sessions"] = sessions or []


@pytest.mark.asyncio
async def test_pending_choice_wins_over_drive_default() -> None:
    db = FakeSession()
    _seed(db, default_session_id="ses_default", flag=True)
    got = await resolve_routed_session_id(db, _job(pending="ses_chosen"))  # type: ignore[arg-type]
    assert got == "ses_chosen"


@pytest.mark.asyncio
async def test_drive_default_routes_without_auto_flag() -> None:
    """The flag gates unattended QUEUEING, not routing: the drive default
    still shapes the rip and the preview when auto-transcode is off."""
    db = FakeSession()
    _seed(db, default_session_id="ses_default", flag=False)
    got = await resolve_routed_session_id(db, _job())  # type: ignore[arg-type]
    assert got == "ses_default"


@pytest.mark.asyncio
async def test_no_default_no_pending_routes_none() -> None:
    db = FakeSession()
    _seed(db, default_session_id=None, flag=True)
    assert await resolve_routed_session_id(db, _job()) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_unknown_drive_routes_none() -> None:
    db = FakeSession()
    db.rows["drives"] = []
    db.rows["config"] = []
    assert await resolve_routed_session_id(db, _job()) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_auto_apply_needs_flag_for_drive_default() -> None:
    db = FakeSession()
    _seed(db, default_session_id="ses_default", flag=False)
    assert await auto_apply_allowed(db, _job()) is False  # type: ignore[arg-type]
    _seed(db, default_session_id="ses_default", flag=True)
    assert await auto_apply_allowed(db, _job()) is True  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_auto_apply_pending_choice_bypasses_flag() -> None:
    """An explicit per-rip session choice is the user opting in for this one
    rip; the global flag must not veto it."""
    db = FakeSession()
    _seed(db, default_session_id=None, flag=False)
    assert await auto_apply_allowed(db, _job(pending="ses_chosen")) is True  # type: ignore[arg-type]


# --- G-02/G-17: session_routes table, resolution order 3-4 --------------------


@pytest.mark.asyncio
async def test_route_resolves_by_media_and_disc_type() -> None:
    db = FakeSession()
    _seed(
        db,
        default_session_id=None,
        flag=True,
        routes=[
            SessionRoute(
                id="srt_a", media_type=MediaType.MUSIC, disc_type=DiscType.CD, session_id="ses_builtin_music_flac"
            ),
        ],
    )
    job = _job(media_type=MediaType.MUSIC, disc_type=DiscType.CD)
    assert await resolve_routed_session_id(db, job) == "ses_builtin_music_flac"  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_drive_default_overrides_route_when_compatible() -> None:
    """The per-drive override (step 2) still wins over any route (step 3-4)
    when the drive default's media_type is compatible with the job's."""
    db = FakeSession()
    _seed(
        db,
        default_session_id="ses_drive_default",
        flag=True,
        routes=[
            SessionRoute(
                id="srt_a", media_type=MediaType.MOVIE, disc_type=DiscType.DVD, session_id="ses_builtin_movie"
            ),
        ],
        sessions=[
            Session(
                id="ses_drive_default",
                name="Drive default",
                media_type=MediaType.MOVIE,
                rip_preset_id="rpr_x",
                output_path_template="{title}",
            )
        ],
    )
    job = _job(media_type=MediaType.MOVIE, disc_type=DiscType.DVD)
    assert await resolve_routed_session_id(db, job) == "ses_drive_default"  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_incompatible_drive_default_falls_through_to_route() -> None:
    """I4 (G-17 unclosed): a movie drive default must not swallow a music
    CD — when the drive default's media_type is incompatible with the job's,
    routing falls through to `session_routes`."""
    db = FakeSession()
    _seed(
        db,
        default_session_id="ses_drive_default_movie",
        flag=True,
        routes=[
            SessionRoute(
                id="srt_a", media_type=MediaType.MUSIC, disc_type=DiscType.CD, session_id="ses_builtin_music_flac"
            ),
        ],
        sessions=[
            Session(
                id="ses_drive_default_movie",
                name="Drive default",
                media_type=MediaType.MOVIE,
                rip_preset_id="rpr_x",
                output_path_template="{title}",
            )
        ],
    )
    job = _job(media_type=MediaType.MUSIC, disc_type=DiscType.CD)
    assert await resolve_routed_session_id(db, job) == "ses_builtin_music_flac"  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_unknown_job_media_type_still_prefers_drive_default() -> None:
    """A job that hasn't been identified yet (media_type=None) has nothing
    to disagree with, so the drive default still wins regardless of the
    drive-default session's own media_type."""
    db = FakeSession()
    _seed(
        db,
        default_session_id="ses_drive_default_movie",
        flag=True,
        routes=[],
        sessions=[
            Session(
                id="ses_drive_default_movie",
                name="Drive default",
                media_type=MediaType.MOVIE,
                rip_preset_id="rpr_x",
                output_path_template="{title}",
            )
        ],
    )
    job = _job(media_type=None, disc_type=DiscType.CD)
    assert await resolve_routed_session_id(db, job) == "ses_drive_default_movie"  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_dangling_drive_default_falls_through_to_route() -> None:
    """A `default_session_id` pointing at a since-deleted session must fall
    through to routes rather than 500 or silently winning."""
    db = FakeSession()
    _seed(
        db,
        default_session_id="ses_gone",
        flag=True,
        routes=[
            SessionRoute(
                id="srt_a", media_type=MediaType.MUSIC, disc_type=DiscType.CD, session_id="ses_builtin_music_flac"
            ),
        ],
        sessions=[],
    )
    job = _job(media_type=MediaType.MUSIC, disc_type=DiscType.CD)
    assert await resolve_routed_session_id(db, job) == "ses_builtin_music_flac"  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_wildcard_route_when_no_exact() -> None:
    db = FakeSession()
    _seed(
        db,
        default_session_id=None,
        flag=True,
        routes=[
            SessionRoute(
                id="srt_wild", media_type=MediaType.MUSIC, disc_type=None, session_id="ses_builtin_music_flac"
            ),
        ],
    )
    # DATA disc, no exact (music, data) route -> falls back to the wildcard.
    job = _job(media_type=MediaType.MUSIC, disc_type=DiscType.DATA)
    assert await resolve_routed_session_id(db, job) == "ses_builtin_music_flac"  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_exact_route_preferred_over_wildcard() -> None:
    db = FakeSession()
    _seed(
        db,
        default_session_id=None,
        flag=True,
        routes=[
            SessionRoute(id="srt_wild", media_type=MediaType.MUSIC, disc_type=None, session_id="ses_wildcard"),
            SessionRoute(id="srt_exact", media_type=MediaType.MUSIC, disc_type=DiscType.CD, session_id="ses_exact"),
        ],
    )
    job = _job(media_type=MediaType.MUSIC, disc_type=DiscType.CD)
    assert await resolve_routed_session_id(db, job) == "ses_exact"  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_no_media_type_skips_routes() -> None:
    """A job that was never identified (media_type=None) must not match the
    wildcard route for any media_type; routing falls through to None."""
    db = FakeSession()
    _seed(
        db,
        default_session_id=None,
        flag=True,
        routes=[
            SessionRoute(
                id="srt_wild", media_type=MediaType.MUSIC, disc_type=None, session_id="ses_builtin_music_flac"
            ),
        ],
    )
    job = _job(media_type=None, disc_type=DiscType.CD)
    assert await resolve_routed_session_id(db, job) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_no_matching_route_returns_none() -> None:
    db = FakeSession()
    _seed(
        db,
        default_session_id=None,
        flag=True,
        routes=[
            SessionRoute(id="srt_a", media_type=MediaType.MOVIE, disc_type=DiscType.BLURAY, session_id="ses_movie"),
        ],
    )
    job = _job(media_type=MediaType.MUSIC, disc_type=DiscType.CD)
    assert await resolve_routed_session_id(db, job) is None  # type: ignore[arg-type]
