"""Coverage for `TranscodeDispatcher.probe()` and `last_spawn_error`.

`/api/system/diagnostics` used to say the transcoder was `ok` even when the
docker host was unreachable or the transcode image was missing there (the
old check only asked "is a dispatcher wired up + are host paths set", never
"can this dispatcher actually run a transcode right now"). `probe()` answers
that question; `last_spawn_error` remembers the most recent spawn failure so
a crash-looping container (image present, spawn itself failing) is visible
too.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import docker.errors  # noqa: E402

from arm_common import SessionApplication, SessionApplicationStatus, TranscodeTask, TranscodeTaskStatus  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402
from tests.test_transcode_dispatcher_full import _disp  # noqa: E402


def _make_dispatcher():
    # _disp builds a TranscodeDispatcher with docker_client=MagicMock(); ARM_TRANSCODE_IMAGE is pinned
    # so the image-check message can be asserted on.
    return _disp(FakeSession(), ARM_TRANSCODE_IMAGE="arm-transcode:test")


def test_probe_ok_when_ping_and_image_succeed() -> None:
    d = _make_dispatcher()
    d._docker.ping.return_value = True
    assert d.probe() == (True, None)


def test_probe_reports_unreachable_host() -> None:
    d = _make_dispatcher()
    d._docker.ping.side_effect = docker.errors.DockerException("ssh: connect refused")
    ok, detail = d.probe()
    assert ok is False and "unreachable" in detail and "connect refused" in detail


def test_probe_reports_missing_image() -> None:
    d = _make_dispatcher()
    d._docker.ping.return_value = True
    d._docker.images.get.side_effect = docker.errors.ImageNotFound("nope")
    ok, detail = d.probe()
    assert ok is False and detail == "image arm-transcode:test not present on docker host"


def test_probe_reports_image_check_failure() -> None:
    """Any other docker-py exception from the image lookup (a flaky remote
    host mid-check, a malformed image reference) is caught too — same
    "the transcoder cannot run right now" answer, distinct detail text."""
    d = _make_dispatcher()
    d._docker.ping.return_value = True
    d._docker.images.get.side_effect = docker.errors.APIError("boom")
    ok, detail = d.probe()
    assert ok is False and detail == "image check failed: boom"


def test_probe_result_is_cached_within_ttl() -> None:
    """/api/system/diagnostics calls probe() on every poll; an unreachable
    ssh host would otherwise stall docker-py's client timeout on each call.
    Two probe() calls inside the TTL window must ping only once."""
    d = _make_dispatcher()
    d._docker.ping.return_value = True
    assert d.probe() == (True, None)
    assert d.probe() == (True, None)
    assert d._docker.ping.call_count == 1
    assert d._docker.images.get.call_count == 1


def test_probe_cache_expires_after_ttl(monkeypatch) -> None:
    d = _make_dispatcher()
    d._docker.ping.return_value = True

    fake_now = {"t": 1000.0}
    monkeypatch.setattr(
        "arm_backend.docker_probe.time.monotonic",
        lambda: fake_now["t"],
    )

    assert d.probe() == (True, None)
    assert d._docker.ping.call_count == 1

    fake_now["t"] += 31.0  # past PROBE_TTL_SECONDS (30.0)
    assert d.probe() == (True, None)
    assert d._docker.ping.call_count == 2


def test_probe_order_pins_unreachable_host_detail_before_image_check() -> None:
    """Both ping and the image lookup are set to fail in the same call — the
    "unreachable" detail (from ping) must win, proving ping runs first and
    the image check is never reached when the host itself is down."""
    d = _make_dispatcher()
    d._docker.ping.side_effect = docker.errors.DockerException("x")
    d._docker.images.get.side_effect = docker.errors.ImageNotFound("y")
    ok, detail = d.probe()
    assert ok is False
    assert detail is not None and "unreachable" in detail
    d._docker.images.get.assert_not_called()


def test_last_spawn_error_defaults_none() -> None:
    assert _make_dispatcher().last_spawn_error is None


async def test_last_spawn_error_set_on_failure_and_cleared_on_next_success() -> None:
    """Drives the spawn loop's except branch (sets last_spawn_error) and then
    its success branch (clears it back to None) in one dispatcher instance —
    covers both the set and the clear line in transcode_dispatcher.py."""
    db = FakeSession()
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_probe",
            session_id="ses_probe",
            job_id="job_01JZXR7K3M5Q8N4VWA00000099",
            status=SessionApplicationStatus.RUNNING,
            overwrite=False,
        )
    ]
    db.rows["gpus"] = []
    now = datetime.now(UTC)
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_fail",
            session_application_id="sap_probe",
            source_track_id="trk_fail",
            status=TranscodeTaskStatus.QUEUED,
            attempts=0,
            progress_pct=0,
            output_path="fail.mkv",
            created_at=now,
        )
    ]
    d = _disp(db, MAX_PARALLEL_TRANSCODES=1)
    d._docker.containers.run.side_effect = RuntimeError("docker daemon unreachable")

    spawned = await d.spawn_pending(db)
    assert spawned == 0
    assert d.last_spawn_error is not None
    assert "docker daemon unreachable" in d.last_spawn_error

    # A second tick with a fresh queued task and a healthy docker client
    # clears the recorded error.
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_ok",
            session_application_id="sap_probe",
            source_track_id="trk_ok",
            status=TranscodeTaskStatus.QUEUED,
            attempts=0,
            progress_pct=0,
            output_path="ok.mkv",
            created_at=now,
        )
    ]
    d._docker.containers.run.side_effect = None
    d._docker.containers.run.return_value = MagicMock()

    spawned = await d.spawn_pending(db)
    assert spawned == 1
    assert d.last_spawn_error is None
