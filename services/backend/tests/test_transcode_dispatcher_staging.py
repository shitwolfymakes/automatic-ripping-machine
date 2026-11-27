"""The dispatcher's staging gate: encode tasks wait for a STAGED source, passthrough waits only on an active
stage, and held tasks neither spawn nor use the encode cap."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from arm_backend.transcode_dispatcher import TranscodeDispatcher, held_for_staging
from arm_backend.ws import WSHub
from arm_common import (
    ContainerFormat,
    MediaType,
    StageStatus,
    TrackStage,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
    TranscodeTool,
)
from tests._fakes import FakeSession
from tests._staged_sources import staged_by_default
from tests.test_transcode_dispatcher import _app_with_one_task, _db_factory, _passthrough_db, _settings


@pytest.fixture(autouse=True)
def _staged_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    staged_by_default(monkeypatch)


def _stage(status: StageStatus, track_id: str = "trk_1", dest: str = "/raw/.staging/j/t.mkv") -> TrackStage:
    return TrackStage(
        track_id=track_id,
        job_id="job_01JZXR7K3M5Q8N4VWA00000001",
        status=status,
        source_path="/raw/j/t.mkv",
        dest_path=dest,
    )


_ENCODE = TranscodePreset(
    id="tpr_x",
    name="Plex 1080p",
    media_type=MediaType.MOVIE,
    is_builtin=True,
    tool=TranscodeTool.HANDBRAKE,
    preset_ref="H.265 MKV 1080p30",
    container=ContainerFormat.MKV,
    encoder="preset",
)


@pytest.mark.parametrize(
    ("stage_status", "encode_held", "passthrough_held"),
    [
        (None, True, False),
        (StageStatus.PENDING, True, True),
        (StageStatus.COPYING, True, True),
        (StageStatus.STALLED, True, True),
        (StageStatus.FAILED, True, False),
        (StageStatus.STAGED, False, False),
    ],
)
def test_held_for_staging_decision(stage_status: StageStatus | None, encode_held: bool, passthrough_held: bool) -> None:
    stage = None if stage_status is None else _stage(stage_status)
    assert held_for_staging(stage, _ENCODE) is encode_held
    assert held_for_staging(stage, None) is passthrough_held


def _encode_db(stages: list[TrackStage] | None) -> FakeSession:
    db = _app_with_one_task(TranscodeTaskStatus.QUEUED, created_at=datetime.now(UTC))
    if stages is not None:
        db.rows["track_stages"] = stages
    return db


@pytest.mark.parametrize(
    "stage_status",
    [None, StageStatus.PENDING, StageStatus.COPYING, StageStatus.STALLED, StageStatus.FAILED],
)
async def test_an_encode_task_waits_until_its_source_is_staged(stage_status: StageStatus | None) -> None:
    db = _encode_db([] if stage_status is None else [_stage(stage_status)])
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())

    assert await disp.spawn_pending(db) == 0

    docker.containers.run.assert_not_called()
    assert db.rows["transcode_tasks"][0].status == TranscodeTaskStatus.QUEUED


async def test_an_encode_task_spawns_once_its_source_is_staged() -> None:
    db = _encode_db([_stage(StageStatus.COPYING)])
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    assert await disp.spawn_pending(db) == 0

    db.rows["track_stages"][0].status = StageStatus.STAGED

    assert await disp.spawn_pending(db) == 1
    docker.containers.run.assert_called_once()


async def test_held_tasks_do_not_consume_the_encode_slots_or_the_scan_cap(caplog: pytest.LogCaptureFixture) -> None:
    db = _encode_db([_stage(StageStatus.PENDING, "trk_1"), _stage(StageStatus.STAGED, "trk_2")])
    db.rows["transcode_tasks"].append(
        TranscodeTask(
            id="txt_2",
            session_application_id="sap_x",
            source_track_id="trk_2",
            status=TranscodeTaskStatus.QUEUED,
            attempts=0,
            progress_pct=0,
            output_path="Iron Man (2008)/Iron Man 2.mkv",
            created_at=datetime.now(UTC) + timedelta(seconds=1),
        )
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(MAX_PARALLEL_TRANSCODES=1), _db_factory(db), docker, WSHub())

    with caplog.at_level(logging.DEBUG, logger="arm_backend.transcode_dispatcher"):
        assert await disp.spawn_pending(db) == 1

    spawned_label = docker.containers.run.call_args.kwargs["labels"]
    assert spawned_label == {"arm.task_id": "txt_2"}
    assert "1 task(s) held waiting for staged files" in caplog.text


async def test_a_task_with_no_stage_row_is_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    db = _encode_db([])
    disp = TranscodeDispatcher(_settings(), _db_factory(db), MagicMock(), WSHub())

    with caplog.at_level(logging.DEBUG, logger="arm_backend.transcode_dispatcher"):
        await disp.spawn_pending(db)
        await disp.spawn_pending(db)

    assert caplog.text.count("task_id=txt_1 has no stage row") == 1


async def test_a_held_task_with_a_stage_row_is_not_logged_as_unstaged(caplog: pytest.LogCaptureFixture) -> None:
    db = _encode_db([_stage(StageStatus.PENDING)])
    disp = TranscodeDispatcher(_settings(), _db_factory(db), MagicMock(), WSHub())

    with caplog.at_level(logging.DEBUG, logger="arm_backend.transcode_dispatcher"):
        await disp.spawn_pending(db)

    assert "has no stage row" not in caplog.text


@pytest.mark.parametrize("stage_status", [StageStatus.PENDING, StageStatus.COPYING, StageStatus.STALLED])
async def test_passthrough_waits_while_a_stage_is_active(tmp_path: Path, stage_status: StageStatus) -> None:
    db, raw = _passthrough_db(tmp_path)
    db.rows["track_stages"] = [_stage(stage_status)]
    disp = TranscodeDispatcher(_settings(MEDIA_ROOT=str(tmp_path / "media")), _db_factory(db), MagicMock(), WSHub())

    await disp.spawn_pending(db)

    assert db.rows["transcode_tasks"][0].status == TranscodeTaskStatus.QUEUED
    assert raw.exists()


@pytest.mark.parametrize("stage_status", [None, StageStatus.FAILED, StageStatus.STAGED])
async def test_passthrough_runs_without_an_active_stage(tmp_path: Path, stage_status: StageStatus | None) -> None:
    db, raw = _passthrough_db(tmp_path)
    db.rows["track_stages"] = [] if stage_status is None else [_stage(stage_status)]
    disp = TranscodeDispatcher(_settings(MEDIA_ROOT=str(tmp_path / "media")), _db_factory(db), MagicMock(), WSHub())

    await disp.spawn_pending(db)

    assert db.rows["transcode_tasks"][0].status == TranscodeTaskStatus.DONE
    assert not raw.exists()


async def test_a_finished_passthrough_releases_the_staged_copy(tmp_path: Path) -> None:
    db, _raw = _passthrough_db(tmp_path)
    staged = tmp_path / "staged.mkv"
    staged.write_bytes(b"data")
    db.rows["track_stages"] = [_stage(StageStatus.STAGED, dest=str(staged))]
    disp = TranscodeDispatcher(_settings(MEDIA_ROOT=str(tmp_path / "media")), _db_factory(db), MagicMock(), WSHub())

    await disp.spawn_pending(db)

    assert not staged.exists()
    assert db.rows["track_stages"] == []


async def test_a_passthrough_whose_commit_fails_keeps_the_staged_copy(tmp_path: Path) -> None:
    db, _raw = _passthrough_db(tmp_path)
    staged = tmp_path / "staged.mkv"
    staged.write_bytes(b"data")
    db.rows["track_stages"] = [_stage(StageStatus.STAGED, dest=str(staged))]
    real_commit = db.commit
    commits = 0

    async def _commit_fails_on_the_terminal_state() -> None:
        nonlocal commits
        commits += 1
        if commits == 2:  # the claim commits first; the terminal state (with the release) second
            raise RuntimeError("commit failed")
        await real_commit()

    db.commit = _commit_fails_on_the_terminal_state  # type: ignore[method-assign]
    disp = TranscodeDispatcher(_settings(MEDIA_ROOT=str(tmp_path / "media")), _db_factory(db), MagicMock(), WSHub())

    await disp.spawn_pending(db)

    assert commits >= 2
    assert staged.exists()


async def test_a_failed_passthrough_keeps_the_staged_copy(tmp_path: Path) -> None:
    db, raw = _passthrough_db(tmp_path)
    raw.unlink()  # the move fails: the source is gone
    staged = tmp_path / "staged.mkv"
    staged.write_bytes(b"data")
    db.rows["track_stages"] = [_stage(StageStatus.STAGED, dest=str(staged))]
    disp = TranscodeDispatcher(_settings(MEDIA_ROOT=str(tmp_path / "media")), _db_factory(db), MagicMock(), WSHub())

    await disp.spawn_pending(db)

    assert db.rows["transcode_tasks"][0].status == TranscodeTaskStatus.FAILED
    assert staged.exists()
    assert len(db.rows["track_stages"]) == 1


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, True),
        ({"ARM_HOST_RAW_PATH": "", "ARM_HOST_STAGING_PATH": "/host/stage"}, True),
        ({"ARM_HOST_RAW_PATH": ""}, False),
        ({"ARM_HOST_MEDIA_PATH": ""}, False),
        ({"ARM_HOST_LOGS_PATH": ""}, False),
        ({"ARM_HOST_CERTS_PATH": ""}, False),
    ],
)
def test_host_paths_need_media_logs_certs_and_raw_or_staging(overrides: dict[str, str], expected: bool) -> None:
    disp = TranscodeDispatcher(_settings(**overrides), MagicMock(), MagicMock(), WSHub())
    assert disp.host_paths_set() is expected


def test_the_transcoder_mounts_staging_read_only_and_never_raw() -> None:
    from arm_backend.transcode_container_spec import task_volumes

    volumes = task_volumes(_settings())
    assert volumes["/host/raw/.staging"] == {"bind": "/staging", "mode": "ro"}
    assert "/raw" not in {mount["bind"] for mount in volumes.values()}


def test_a_staging_path_outside_raw_is_the_staging_mount() -> None:
    from arm_backend.transcode_container_spec import task_volumes

    volumes = task_volumes(_settings(ARM_HOST_STAGING_PATH="/mnt/fast"))
    assert volumes["/mnt/fast"] == {"bind": "/staging", "mode": "ro"}
    assert "/host/raw" not in volumes
