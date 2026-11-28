"""The version policy end to end: snapshotted at creation, recomputed through the resolver claims when the title
map arrives, when a session is applied and when the card's switch changes, with the operator's own ticks kept."""

from __future__ import annotations

import secrets
from typing import Any

import pytest
from fastapi.testclient import TestClient

from arm_backend.auto_session import _refresh_version_ticks, apply_session_internal
from arm_backend.identity.proposals import claims_of, record_manual_track
from arm_backend.track_selection import select_tracks_for_review
from arm_backend.version_policy import prefers_stereo_3d, selection_policy, version_set_refs
from arm_common import (
    DiscType,
    Job,
    JobStatus,
    MediaType,
    Session,
    SessionApplication,
    SessionApplicationStatus,
    TrackStatus,
    TranscodePreset,
)
from arm_common.enums import ContainerFormat, TranscodeTool
from arm_common.models import Track
from arm_common.schemas import ScanResult
from arm_common.title_classes import TitleClass
from tests._fakes import FakeSession
from tests.bd_structure_scans import EXTRA, OTHER_ANGLE, PICK, SUBSET, br3d_structure_scan
from tests.test_jobs_router import _auth, _Hub
from tests.test_jobs_router import _make_app as _jobs_app
from tests.test_playlist_first_identify import JOB_ID, _by_ref, _mkv_titles, _post_titles, _structure_job
from tests.test_ripper_router import (
    _config,
    _drive,
    _Dispatcher,
    _make_app,
    _movie_preset,
    _OWNER_HEADERS,
    _SERVICE_AUTH,
)
from arm_backend.metadata.base import MetadataResult

_ALL = {EXTRA, PICK, OTHER_ANGLE, SUBSET}


def _operator_ticks(job: Job, track: Track, *, excluded: bool) -> None:
    """What the card's PATCH does: a manual claim, then the resolver applies it to the row."""
    record_manual_track(job, track, {"excluded": excluded})
    track.excluded = excluded


def _ticked(db: FakeSession) -> set[str]:
    return {t.source_ref for t in db.rows["tracks"] if not t.excluded}


def _preset(tool: TranscodeTool) -> TranscodePreset:
    return TranscodePreset(
        id=f"tpr_{tool.value}",
        name=tool.value,
        media_type=MediaType.MOVIE,
        is_builtin=False,
        tool=tool,
        container=ContainerFormat.MKV,
    )


def _session(preset: TranscodePreset | None) -> Session:
    return Session(
        id="ses_x",
        name="s",
        media_type=MediaType.MOVIE,
        rip_preset_id="rpr_builtin_movie_archive",
        transcode_preset_id=None if preset is None else preset.id,
        output_path_template="{title}",
    )


# --- snapshot at creation ---


def _identify(db: FakeSession, scan: ScanResult, **config: Any) -> Any:
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(hold_for_review=True)]
    db.rows["config"][0].tick_one_version = config.get("tick_one_version", True)

    app = _make_app(db, dispatcher=_Dispatcher(MetadataResult(title="Feature", year=2017, kind="movie", payload={})))
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": scan.model_dump(mode="json")},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200, r.text
    return r


def _with_rip_preset(db: FakeSession) -> None:
    db.rows["rip_presets"] = [_movie_preset()]


@pytest.mark.parametrize("default, expected_ticks", [(True, {EXTRA, PICK}), (False, _ALL)])
def test_a_new_blu_ray_job_snapshots_the_global_default_and_ticks_by_it(
    default: bool, expected_ticks: set[str]
) -> None:
    db = FakeSession()
    _with_rip_preset(db)
    _identify(db, br3d_structure_scan(), tick_one_version=default)
    job = db.rows["jobs"][0]
    assert job.tick_one_version is default
    tracks = {t.source_ref: t for t in db.added if isinstance(t, Track)}
    assert {r for r, t in tracks.items() if not t.excluded} == expected_ticks


def test_a_dvd_job_snapshots_the_default_and_a_cd_job_does_not() -> None:
    from tests.test_ripper_router import _scan_dict

    for disc_type, expected in (("dvd", False), ("cd", None)):
        db = FakeSession()
        _with_rip_preset(db)
        db.rows["drives"] = [_drive()]
        db.rows["config"] = [_config()]
        db.rows["config"][0].tick_one_version = False
        scan = _scan_dict(disc_type)
        with TestClient(_make_app(db, dispatcher=_Dispatcher())) as client:
            client.post("/api/ripper/identify", json={"drive_id": "drv_x", "scan_result": scan}, headers=_SERVICE_AUTH)
        assert db.rows["jobs"][0].tick_one_version is expected


# --- the title map arrives ---


def test_the_title_map_moves_an_unrippable_pick_to_its_first_rippable_alternate() -> None:
    """MakeMKV lists neither angle of 00334.mpls, so the pick and its other angle are out and the copy
    without chapters stands in."""
    db = FakeSession()
    job = _structure_job(br3d_structure_scan(), db=db)
    job.tick_one_version = True
    with TestClient(_make_app(db)) as client:
        _post_titles(client, {"titles": _mkv_titles(drop="00334.mpls")})
    claims = claims_of(job).sources["preset"].tracks
    assert [claims[r].selected for r in (EXTRA, PICK, OTHER_ANGLE, SUBSET)] == [True, False, False, True]
    assert _ticked(db) == {EXTRA, SUBSET}


def test_the_title_map_keeps_an_operator_choice_on_a_rippable_ref() -> None:
    db = FakeSession()
    job = _structure_job(br3d_structure_scan(), db=db)
    job.tick_one_version = True
    other = _by_ref(db)[OTHER_ANGLE]
    _operator_ticks(job, other, excluded=False)
    with TestClient(_make_app(db)) as client:
        _post_titles(client, {"titles": _mkv_titles()})
    assert other.excluded is False
    assert _ticked(db) == {EXTRA, PICK, OTHER_ANGLE}


def test_the_title_map_recomputes_with_every_version_on() -> None:
    db = FakeSession()
    job = _structure_job(br3d_structure_scan(), db=db)
    job.tick_one_version = False
    with TestClient(_make_app(db)) as client:
        _post_titles(client, {"titles": _mkv_titles(drop="00342.mpls")})
    assert _ticked(db) == {EXTRA, PICK, OTHER_ANGLE}
    assert _by_ref(db)[SUBSET].excluded is True


# --- the card's switch ---


def _toggle_app(
    job_tick: bool = True, status: JobStatus = JobStatus.AWAITING_REVIEW
) -> tuple[FakeSession, Job, Any, str, _Hub]:
    db = FakeSession()
    job = _structure_job(br3d_structure_scan(), status=status, db=db)
    job.tick_one_version = job_tick
    if not job_tick:
        fresh = select_tracks_for_review(JOB_ID, br3d_structure_scan(), _movie_preset(), tick_one_version=False)
        for track, new in zip(db.rows["tracks"], fresh):
            track.excluded = new.excluded
    hub = _Hub()
    app, token = _jobs_app(secrets.token_bytes(32), db, hub=hub)
    return db, job, app, token, hub


def _patch(app: Any, token: str, body: dict[str, Any]) -> Any:
    with TestClient(app) as client:
        return client.patch(f"/api/jobs/{JOB_ID}", json=body, headers=_auth(token))


def test_switching_to_every_version_ticks_every_member_of_the_set_and_nothing_else() -> None:
    db, job, app, token, hub = _toggle_app(True)
    assert _ticked(db) == {EXTRA, PICK}
    r = _patch(app, token, {"tick_one_version": False})
    assert r.status_code == 200, r.text
    assert r.json()["tick_one_version"] is False
    assert job.tick_one_version is False
    assert _ticked(db) == _ALL
    assert {e["payload"]["track_id"] for e in hub.events if e["event_type"] == "track.updated"} >= {"trk_2", "trk_3"}


def test_switching_back_to_one_version_drops_the_alternates() -> None:
    db, job, app, token, _ = _toggle_app(False)
    assert _ticked(db) == _ALL
    assert _patch(app, token, {"tick_one_version": False}).status_code == 200  # a restated value changes nothing
    assert _ticked(db) == _ALL
    r = _patch(app, token, {"tick_one_version": True})
    assert r.status_code == 200, r.text
    assert _ticked(db) == {EXTRA, PICK}


def test_the_toggle_reverts_manual_ticks_on_set_members_only() -> None:
    db, job, app, token, _ = _toggle_app(True)
    tracks = _by_ref(db)
    # The operator ticked the other angle and unticked the extra (not a member of any set).
    _operator_ticks(job, tracks[OTHER_ANGLE], excluded=False)
    _operator_ticks(job, tracks[EXTRA], excluded=True)
    r = _patch(app, token, {"tick_one_version": False})
    assert r.status_code == 200, r.text
    manual = claims_of(job).sources["manual"].tracks
    assert OTHER_ANGLE not in manual
    assert manual[EXTRA].selected is False
    assert tracks[EXTRA].excluded is True
    assert tracks[PICK].excluded is False


def test_a_track_edit_in_the_same_request_survives_the_toggle() -> None:
    db, job, app, token, _ = _toggle_app(False)
    extra = _by_ref(db)[EXTRA]
    r = _patch(app, token, {"tick_one_version": True, "tracks": [{"track_id": extra.id, "excluded": True}]})
    assert r.status_code == 200, r.text
    assert _ticked(db) == {PICK}


@pytest.mark.parametrize("status", [JobStatus.RIPPING, JobStatus.RIPPED, JobStatus.FAILED])
def test_the_toggle_is_refused_once_the_rip_has_started(status: JobStatus) -> None:
    db, job, app, token, _ = _toggle_app(True, status=status)
    r = _patch(app, token, {"tick_one_version": False})
    assert r.status_code == 409
    assert _ticked(db) == {EXTRA, PICK}


def test_the_toggle_is_refused_for_a_disc_that_is_not_video() -> None:
    db, job, app, token, _ = _toggle_app(True)
    job.disc_type = DiscType.CD
    assert _patch(app, token, {"tick_one_version": False}).status_code == 409


def test_the_switch_cannot_be_cleared() -> None:
    db, job, app, token, _ = _toggle_app(True)
    assert _patch(app, token, {"tick_one_version": None}).status_code == 422
    assert job.tick_one_version is True


def test_the_toggle_on_a_job_without_a_stored_scan_changes_the_flag_only() -> None:
    db, job, app, token, _ = _toggle_app(True)
    job.metadata_json = {}
    r = _patch(app, token, {"tick_one_version": False})
    assert r.status_code == 200, r.text
    assert job.tick_one_version is False


# --- the 2D/3D signal (D60) ---


@pytest.mark.anyio
async def test_a_transcode_session_prefers_2d_and_passthrough_or_none_prefers_3d() -> None:
    db = FakeSession()
    db.rows["transcode_presets"] = [_preset(TranscodeTool.HANDBRAKE), _preset(TranscodeTool.NONE)]
    assert await prefers_stereo_3d(db, _session(_preset(TranscodeTool.HANDBRAKE))) is False  # type: ignore[arg-type]
    assert await prefers_stereo_3d(db, _session(_preset(TranscodeTool.NONE))) is True  # type: ignore[arg-type]
    assert await prefers_stereo_3d(db, _session(None)) is True  # type: ignore[arg-type]
    assert await prefers_stereo_3d(db, None) is True  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_selection_policy_reads_the_job_and_the_session_on_a_blu_ray_only() -> None:
    db = FakeSession()
    db.rows["transcode_presets"] = [_preset(TranscodeTool.HANDBRAKE)]
    job = Job(
        id=JOB_ID, drive_id="drv_x", disc_type=DiscType.BLURAY, status=JobStatus.AWAITING_REVIEW, tick_one_version=False
    )
    _park(db, job, _session(_preset(TranscodeTool.HANDBRAKE)))
    assert await selection_policy(db, job) == {"tick_one_version": False, "prefer_stereo_3d": False}  # type: ignore[arg-type]
    job.disc_type = DiscType.DVD
    job.tick_one_version = None
    assert await selection_policy(db, job) == {"tick_one_version": True, "prefer_stereo_3d": None}  # type: ignore[arg-type]


# --- session apply ---


def _park(db: FakeSession, job: Job, sess: Session) -> None:
    """A session applied before the rip: a waiting_identify application, the one the rip-complete drain fans out."""
    db.rows.setdefault("sessions", []).append(sess)
    db.rows.setdefault("session_applications", []).append(
        SessionApplication(
            id="sap_x", session_id=sess.id, job_id=job.id, status=SessionApplicationStatus.WAITING_IDENTIFY
        )
    )


def _twin_scan() -> ScanResult:
    from arm_common.schemas import BdClip, BdPlaylist

    def pl(name: str, mvc: list[int]) -> BdPlaylist:
        return BdPlaylist(
            name=name,
            clips=[10, 11],
            clip_seconds=[3600.0, 3600.0],
            duration_seconds=7200,
            chapter_count=20,
            mvc_clips=mvc,
        )

    return ScanResult(
        disc_type=DiscType.BLURAY,
        playlists=[pl("00100.mpls", []), pl("00101.mpls", [12])],
        clips=[
            BdClip(number=10, seconds=3600.0, size_bytes=1),
            BdClip(number=11, seconds=3600.0, size_bytes=1),
            BdClip(number=12, seconds=3600.0, size_bytes=1, mvc=True),
        ],
    )


@pytest.mark.anyio
async def test_applying_a_session_before_the_rip_recomputes_the_2d_3d_pick_and_the_classes() -> None:
    db = FakeSession()
    job = _structure_job(_twin_scan(), db=db)
    job.tick_one_version = True
    tracks = db.rows["tracks"]
    by_ref = {t.source_ref: t for t in tracks}
    assert {r for r, t in by_ref.items() if not t.excluded} == {"00100.mpls"}
    hub = _Hub()
    _park(db, job, _session(_preset(TranscodeTool.NONE)))
    db.rows["transcode_presets"] = [_preset(TranscodeTool.NONE)]
    await _refresh_version_ticks(db, hub, job, tracks)  # type: ignore[arg-type]
    assert {t.source_ref for t in tracks if not t.excluded} == {"00101.mpls"}
    assert by_ref["00100.mpls"].title_class == TitleClass.VIEW
    assert any(e["event_type"] == "track.updated" for e in hub.events)


@pytest.mark.anyio
async def test_applying_a_session_after_the_rip_leaves_the_ticks_alone() -> None:
    db = FakeSession()
    job = _structure_job(_twin_scan(), status=JobStatus.RIPPED, db=db)
    before = {t.source_ref: t.excluded for t in db.rows["tracks"]}
    await _refresh_version_ticks(db, None, job, db.rows["tracks"])  # type: ignore[arg-type]
    assert {t.source_ref: t.excluded for t in db.rows["tracks"]} == before


# --- version sets from the track columns ---


def test_version_set_refs_are_the_picks_and_alternates_of_the_tracks() -> None:
    db = FakeSession()
    _structure_job(br3d_structure_scan(), db=db)
    assert version_set_refs(db.rows["tracks"]) == {PICK, OTHER_ANGLE, SUBSET}


def test_version_set_refs_include_every_edition() -> None:
    def track(index: int, cls: TitleClass, ref: str | None = None) -> Track:
        return Track(
            id=f"t{index}",
            job_id="j",
            kind="video_title",
            index=index,
            source_ref=str(index),
            title_class=cls,
            title_class_ref=ref,
        )  # type: ignore[arg-type]

    tracks = [track(0, TitleClass.EDITION), track(1, TitleClass.EDITION), track(2, TitleClass.PRIMARY)]
    assert version_set_refs(tracks) == {"0", "1"}


def test_a_status_that_started_the_rip_is_not_a_policy_status() -> None:
    from arm_backend.version_policy import policy_applies

    job = Job(id="j", drive_id="d", disc_type=DiscType.BLURAY, status=JobStatus.RIPPING)
    assert not policy_applies(job)
    job.status = JobStatus.IDENTIFIED
    assert policy_applies(job)
    assert TrackStatus.QUEUED  # keeps the import honest


# --- rip-start selects with the job's policy when no review tracks exist ---


@pytest.mark.parametrize("one, expected", [(True, {EXTRA, PICK}), (False, _ALL)])
def test_rip_start_without_review_tracks_selects_by_the_jobs_policy(
    monkeypatch: pytest.MonkeyPatch, one: bool, expected: set[str]
) -> None:
    from arm_backend.routers import ripper as ripper_router

    real_select = ripper_router.select_rip_tracks

    def _select(*args: Any, **kwargs: Any) -> list[Track]:
        tracks = real_select(*args, **kwargs)
        for n, track in enumerate(tracks):
            track.id, track.status, track.attempts = f"trk_{n}", TrackStatus.QUEUED, 0
        return tracks

    monkeypatch.setattr(ripper_router, "select_rip_tracks", _select)
    db = FakeSession()
    job = _structure_job(br3d_structure_scan(), status=JobStatus.IDENTIFIED, with_tracks=False, db=db)
    job.tick_one_version = one
    with TestClient(_make_app(db)) as client:
        _post_titles(client, {"titles": _mkv_titles()})
        r = client.post(f"/api/ripper/jobs/{JOB_ID}/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 200, r.text
    assert {t["source_ref"] for t in r.json()["tracks"] if not t["excluded"]} == expected


# --- recompute does nothing it cannot decide ---


@pytest.mark.anyio
async def test_recompute_without_a_seeded_rip_preset_changes_nothing() -> None:
    from arm_backend.version_policy import recompute_ticks

    db = FakeSession()
    job = _structure_job(br3d_structure_scan(), db=db)
    db.rows["rip_presets"] = []
    assert await recompute_ticks(db, job, db.rows["tracks"], br3d_structure_scan(), rippable=None) == set()  # type: ignore[arg-type]
    assert "preset" not in claims_of(job).sources


@pytest.mark.anyio
async def test_recompute_for_a_preset_that_takes_the_disc_whole_changes_nothing() -> None:
    from arm_backend.version_policy import recompute_ticks
    from arm_common import OutputMode

    db = FakeSession()
    job = _structure_job(br3d_structure_scan(), db=db)
    db.rows["rip_presets"][0].output_mode = OutputMode.ISO
    assert await recompute_ticks(db, job, db.rows["tracks"], br3d_structure_scan(), rippable=None) == set()  # type: ignore[arg-type]
    assert "preset" not in claims_of(job).sources


@pytest.mark.anyio
async def test_applying_a_session_without_a_hub_still_recomputes() -> None:
    db = FakeSession()
    job = _structure_job(_twin_scan(), db=db)
    db.rows["transcode_presets"] = [_preset(TranscodeTool.NONE)]
    _park(db, job, _session(_preset(TranscodeTool.NONE)))
    await _refresh_version_ticks(db, None, job, db.rows["tracks"])  # type: ignore[arg-type]
    assert {t.source_ref for t in db.rows["tracks"] if not t.excluded} == {"00101.mpls"}


@pytest.mark.anyio
@pytest.mark.parametrize("tool, picked", [(TranscodeTool.HANDBRAKE, "00100.mpls"), (TranscodeTool.NONE, "00101.mpls")])
async def test_a_parked_session_decides_the_2d_3d_pick(tool: TranscodeTool, picked: str) -> None:
    db = FakeSession()
    job = _structure_job(_twin_scan(), db=db)
    job.tick_one_version = True
    db.rows["transcode_presets"] = [_preset(tool)]
    _park(db, job, _session(_preset(tool)))
    await _refresh_version_ticks(db, None, job, db.rows["tracks"])  # type: ignore[arg-type]
    assert {t.source_ref for t in db.rows["tracks"] if not t.excluded} == {picked}


@pytest.mark.anyio
async def test_no_session_keeps_the_3d_pick() -> None:
    db = FakeSession()
    job = _structure_job(_twin_scan(), db=db)
    job.tick_one_version = True
    db.rows["transcode_presets"] = []
    assert (await selection_policy(db, job))["prefer_stereo_3d"] is True  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_a_parked_session_wins_over_the_routed_one(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()
    job = Job(id=JOB_ID, drive_id="drv_x", disc_type=DiscType.BLURAY, status=JobStatus.AWAITING_REVIEW)
    db.rows["transcode_presets"] = [_preset(TranscodeTool.HANDBRAKE), _preset(TranscodeTool.NONE)]
    routed = _session(_preset(TranscodeTool.NONE))

    async def load_routed(_db: Any, _job: Job) -> Session:
        return routed

    monkeypatch.setattr("arm_backend.version_policy.load_routed_session", load_routed)
    assert (await selection_policy(db, job))["prefer_stereo_3d"] is True  # type: ignore[arg-type]
    _park(db, job, _session(_preset(TranscodeTool.HANDBRAKE)))
    assert (await selection_policy(db, job))["prefer_stereo_3d"] is False  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_parking_a_passthrough_session_before_the_rip_moves_the_pick_to_3d(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeSession()
    job = _structure_job(_twin_scan(), db=db)
    job.tick_one_version = True
    sess = _session(_preset(TranscodeTool.NONE))
    db.rows["sessions"] = [sess]
    db.rows["transcode_presets"] = [_preset(TranscodeTool.NONE)]
    outcome = await apply_session_internal(
        db,
        job=job,
        session_id=sess.id,
        created_by_user_id=None,
        source="manual",  # type: ignore[arg-type]
    )
    assert outcome.application is not None
    assert outcome.application.status == SessionApplicationStatus.WAITING_IDENTIFY
    assert {t.source_ref for t in db.rows["tracks"] if not t.excluded} == {"00101.mpls"}
