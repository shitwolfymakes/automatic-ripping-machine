"""Backend-spawned per-device GPU probe.

The runner starts one short-lived transcode container per GPU row in
`--probe-device` mode, parses the single JSON line it prints, and writes the
verified codec list (or a readable error) onto the row. These tests drive it
with a fake docker client: the container's exit code, stdout, and `wait`
behavior are all scripted.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from sqlalchemy.orm.exc import StaleDataError  # noqa: E402

from arm_backend import gpu_probe_runner as runner_mod  # noqa: E402
from arm_backend.config import Settings  # noqa: E402
from arm_backend.gpu_probe_runner import PROBE_TIMEOUT_S, GpuProbeRunner  # noqa: E402
from arm_backend.transcode_dispatcher import TranscodeDispatcher  # noqa: E402
from arm_common import Gpu  # noqa: E402
from arm_common.enums import GpuStatus, GpuVendor  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

STALE = "probe failed (exit {n}); the transcode image may predate --probe-device: rebuild or pull it"


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "DATABASE_URL": "postgresql://x:x@localhost/x",
        "ARM_SERVICE_TOKEN": "tok-service",
        "ARM_TRANSCODE_IMAGE": "arm-transcode:latest",
        "ARM_TRANSCODE_IMAGE_QSV": "",
        "ARM_TRANSCODE_IMAGE_VAAPI": "",
        "ARM_TRANSCODE_IMAGE_NVENC": "",
        "ARM_TRANSCODE_CAPABLE": True,
        "ARM_TRANSCODE_DOCKER_HOST": "",
        "ARM_TRANSCODE_PUID": "",
        "ARM_TRANSCODE_PGID": "",
        "ARM_RENDER_GID": "",
        "ARM_LOG_LEVEL": "info",
        "ARM_DOCKER_NETWORK": "armv3_default",
        "ARM_TRANSCODE_DISPATCH_INTERVAL_SECONDS": 5,
    }
    base.update(overrides)
    return Settings.model_construct(**base)


def _db_factory(db: FakeSession) -> Any:
    class _Factory:
        def __call__(self) -> _Factory:
            return self

        async def __aenter__(self) -> FakeSession:
            return db

        async def __aexit__(self, *exc: Any) -> None:
            return None

    return _Factory()


class _Container:
    def __init__(
        self,
        *,
        status: int | None = 0,
        stdout: bytes = b"",
        stderr: bytes = b"",
        wait_exc: Exception | None = None,
        labels: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.stdout = stdout
        self.stderr = stderr
        self.labels = labels or {}
        self.wait_exc = wait_exc
        self.wait_timeouts: list[object] = []
        self.logs_calls: list[dict[str, bool]] = []
        self.removed: list[bool] = []
        self.remove_exc: Exception | None = None

    def wait(self, timeout: object = None) -> dict[str, int | None]:
        self.wait_timeouts.append(timeout)
        if self.wait_exc is not None:
            raise self.wait_exc
        return {"StatusCode": self.status}

    def logs(self, *, stdout: bool, stderr: bool) -> bytes:
        self.logs_calls.append({"stdout": stdout, "stderr": stderr})
        return self.stdout if stdout else self.stderr

    def remove(self, *, force: bool) -> None:
        self.removed.append(force)
        if self.remove_exc is not None:
            raise self.remove_exc


class _Containers:
    def __init__(self, container: _Container) -> None:
        self.container = container
        self.calls: list[dict[str, Any]] = []
        self.run_exc: Exception | None = None
        self.on_run: Callable[[dict[str, Any]], None] | None = None
        self.existing: list[_Container] = []
        self.list_calls: list[dict[str, Any]] = []
        self.list_exc: Exception | None = None

    def list(self, **kwargs: Any) -> list[_Container]:
        self.list_calls.append(kwargs)
        if self.list_exc is not None:
            raise self.list_exc
        return self.existing

    def run(self, **kwargs: Any) -> _Container:
        self.calls.append(kwargs)
        if self.on_run is not None:
            self.on_run(kwargs)
        if self.run_exc is not None:
            raise self.run_exc
        return self.container


class _Docker:
    def __init__(self, container: _Container) -> None:
        self.containers = _Containers(container)


class _Hub:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    async def emit(self, *, topic: str, event_type: str, payload: dict[str, Any], session: object) -> None:
        self.events.append((topic, event_type, payload))


def _gpu(gpu_id: str = "gpu_1", vendor: GpuVendor = GpuVendor.QSV, **kw: Any) -> Gpu:
    defaults: dict[str, Any] = {
        "id": gpu_id,
        "vendor": vendor,
        "device_path": "/dev/dri/renderD128",
        "encoder_kinds": [],
        "status": GpuStatus.AVAILABLE,
        "enabled": True,
        "probed_at": None,
    }
    defaults.update(kw)
    return Gpu(**defaults)


def _payload(verified: list[str], errors: dict[str, str] | None = None) -> bytes:
    return json.dumps({"verified": verified, "errors": errors or {}}).encode()


def _build(
    gpus: list[Gpu],
    container: _Container | None = None,
    *,
    docker: bool = True,
    image_exists: Callable[[str], bool] | None = None,
    **settings_kw: Any,
) -> tuple[GpuProbeRunner, FakeSession, _Docker | None, _Hub, TranscodeDispatcher]:
    db = FakeSession()
    db.rows["gpus"] = gpus
    settings = _settings(**settings_kw)
    fake_docker = _Docker(container or _Container(stdout=_payload(["h265"]))) if docker else None
    hub = _Hub()
    dispatcher = TranscodeDispatcher(
        settings=settings,
        db_factory=_db_factory(db),
        docker_client=fake_docker,
        hub=hub,  # type: ignore[arg-type]
    )
    dispatcher.image_exists = image_exists or (lambda _image: False)  # type: ignore[method-assign]
    runner = GpuProbeRunner(settings, _db_factory(db), dispatcher, hub)  # type: ignore[arg-type]
    return runner, db, fake_docker, hub, dispatcher


# --- result parsing and the row write ----------------------------------------


async def test_verified_json_writes_row_and_emits() -> None:
    container = _Container(stdout=b"entrypoint noise\n" + _payload(["h265"], {"qsv_h264": "no h264"}) + b"\n\n")
    runner, db, _docker, hub, dispatcher = _build([_gpu(encoder_kinds=["stale"], probe_error="old")], container)
    seen_probing: list[bool] = []
    assert _docker is not None
    _docker.containers.on_run = lambda _kw: seen_probing.append("gpu_1" in dispatcher.probing_gpu_ids)

    await runner.probe_gpu("gpu_1")

    row = db.rows["gpus"][0]
    assert row.encoder_kinds == ["h265"]
    assert row.probed_at is not None
    assert row.probe_error is None
    assert hub.events == [("transcode.events", "gpu.probed", {"gpu_id": "gpu_1"})]
    assert seen_probing == [True]  # reserved while the container ran
    assert dispatcher.probing_gpu_ids == set()  # released afterwards
    assert container.wait_timeouts == [PROBE_TIMEOUT_S]
    assert container.logs_calls == [{"stdout": True, "stderr": False}]
    assert container.removed == [True]


async def test_duplicate_codecs_collapse_and_unknown_ones_are_dropped_and_noted() -> None:
    verified = ["h264", "h264", 5, "vp9", "h265", "vp9"]
    container = _Container(stdout=json.dumps({"verified": verified, "errors": {}}).encode())
    runner, db, *_ = _build([_gpu()], container)
    await runner.probe_gpu("gpu_1")
    row = db.rows["gpus"][0]
    assert row.encoder_kinds == ["h264", "h265"]
    assert row.probe_error == "ignored unknown codec(s) from the probe: 5, vp9"


async def test_only_unknown_codecs_counts_as_nothing_verified() -> None:
    container = _Container(stdout=_payload(["mpeg2"], {"qsv_h264": "init failed"}))
    runner, db, *_ = _build([_gpu()], container)
    await runner.probe_gpu("gpu_1")
    row = db.rows["gpus"][0]
    assert row.encoder_kinds == []
    assert row.probe_error == (
        "no encoder verified: qsv_h264: init failed; ignored unknown codec(s) from the probe: mpeg2"
    )


async def test_nothing_verified_summarises_errors() -> None:
    errors = {"qsv_h264": "init failed | device busy", "qsv_h265": "x" * 900}
    runner, db, _docker, hub, _d = _build([_gpu(encoder_kinds=["h264"])], _Container(stdout=_payload([], errors)))

    await runner.probe_gpu("gpu_1")

    row = db.rows["gpus"][0]
    assert row.encoder_kinds == []
    assert row.probed_at is not None
    assert row.probe_error is not None
    assert row.probe_error.startswith("no encoder verified: qsv_h264: init failed | device busy; qsv_h265: xxx")
    assert len(row.probe_error) == 500
    assert hub.events[0][1] == "gpu.probed"


async def test_nothing_verified_without_errors_still_explains() -> None:
    runner, db, *_ = _build([_gpu()], _Container(stdout=json.dumps({"verified": []}).encode()))
    await runner.probe_gpu("gpu_1")
    assert db.rows["gpus"][0].probe_error == "no encoder verified"


@pytest.mark.parametrize(
    ("status", "stdout", "stderr", "expected"),
    [
        # An argument parser rejecting the unknown mode.
        (
            2,
            b"",
            b"usage: main.py\nmain.py: error: unrecognized arguments: --probe-device\n",
            STALE.format(n=2) + "; stderr: usage: main.py | main.py: error: unrecognized arguments: --probe-device",
        ),
        # An old worker ignoring the flag and running a transcode without a task.
        (
            1,
            b"Traceback (most recent call last):\n",
            b"Traceback (most recent call last):\nKeyError: 'ARM_TRANSCODE_TASK_ID'\n",
            STALE.format(n=1) + "; stderr: Traceback (most recent call last): | KeyError: 'ARM_TRANSCODE_TASK_ID'",
        ),
        (0, b"not json at all", b"", STALE.format(n=0)),
        (0, b"{}", b"", STALE.format(n=0)),  # the legacy --probe-encoders shape
        (0, b"[1, 2]", b"", STALE.format(n=0)),
        (0, b"", b"", STALE.format(n=0)),
        (1, _payload(["h265"]), b"", STALE.format(n=1)),  # a non-zero exit never counts as verified
    ],
)
async def test_stale_image_or_failed_probe_says_to_rebuild(
    status: int, stdout: bytes, stderr: bytes, expected: str
) -> None:
    container = _Container(status=status, stdout=stdout, stderr=stderr)
    runner, db, _docker, hub, _d = _build([_gpu(encoder_kinds=["h264"])], container)

    await runner.probe_gpu("gpu_1")

    row = db.rows["gpus"][0]
    assert row.encoder_kinds == []
    assert row.probed_at is not None
    assert row.probe_error == expected
    assert hub.events[0][1] == "gpu.probed"
    assert container.logs_calls == [{"stdout": True, "stderr": False}, {"stdout": False, "stderr": True}]


async def test_exit_3_reports_the_test_clip_failure_with_stderr() -> None:
    stderr = b"line1\nline2\nline3\nline4\nline5\ncould not generate the test clip: \xff libavfilter missing\n"
    runner, db, *_ = _build([_gpu()], _Container(status=3, stderr=stderr))
    await runner.probe_gpu("gpu_1")
    assert db.rows["gpus"][0].probe_error == (
        "probe could not create its test clip: line2 | line3 | line4 | line5 | "
        "could not generate the test clip: \ufffd libavfilter missing"
    )


async def test_exit_3_without_stderr() -> None:
    runner, db, *_ = _build([_gpu()], _Container(status=3))
    await runner.probe_gpu("gpu_1")
    assert db.rows["gpus"][0].probe_error == "probe could not create its test clip"


async def test_exit_2_reports_a_misconfigured_probe() -> None:
    stderr = b"--probe-device: unknown ARM_GPU_VENDOR='xyz' (valid: qsv, nvenc, vaapi)\n"
    runner, db, *_ = _build([_gpu()], _Container(status=2, stderr=stderr))
    await runner.probe_gpu("gpu_1")
    assert db.rows["gpus"][0].probe_error == (
        "probe misconfigured: --probe-device: unknown ARM_GPU_VENDOR='xyz' (valid: qsv, nvenc, vaapi)"
    )


async def test_exit_2_without_stderr() -> None:
    runner, db, *_ = _build([_gpu()], _Container(status=2))
    await runner.probe_gpu("gpu_1")
    assert db.rows["gpus"][0].probe_error == "probe misconfigured"


async def test_long_stderr_is_truncated_to_500_chars() -> None:
    runner, db, *_ = _build([_gpu()], _Container(status=1, stderr=b"e" * 2000))
    await runner.probe_gpu("gpu_1")
    error = db.rows["gpus"][0].probe_error
    assert error is not None and len(error) == 500
    assert error.startswith(STALE.format(n=1))


@pytest.mark.parametrize("result", [{}, {"StatusCode": None}])
async def test_missing_status_code_is_reported_as_unknown_exit(result: dict[str, Any]) -> None:
    container = _Container(stdout=b"")
    container.wait = lambda timeout=None: result  # type: ignore[method-assign]
    runner, db, *_ = _build([_gpu()], container)
    await runner.probe_gpu("gpu_1")
    assert db.rows["gpus"][0].probe_error == STALE.format(n=-1)


async def test_wait_timeout_removes_container_and_records_timeout() -> None:
    class ReadTimeout(Exception):
        pass

    container = _Container(wait_exc=ReadTimeout("UnixHTTPConnectionPool: Read timed out."))
    runner, db, *_ = _build([_gpu(encoder_kinds=["h264"])], container)

    await runner.probe_gpu("gpu_1")

    row = db.rows["gpus"][0]
    assert container.removed == [True]
    assert container.logs_calls == []
    assert row.encoder_kinds == []
    assert row.probe_error is not None
    assert f"timed out after {PROBE_TIMEOUT_S} s" in row.probe_error


@pytest.mark.parametrize("exc", [TimeoutError("slow"), ConnectionError("Read timed out. (read timeout=120)")])
async def test_other_timeout_shapes_are_recognised(exc: Exception) -> None:
    runner, db, *_ = _build([_gpu()], _Container(wait_exc=exc))
    await runner.probe_gpu("gpu_1")
    assert "timed out after 120 s" in (db.rows["gpus"][0].probe_error or "")


async def test_wait_failure_that_is_not_a_timeout_is_recorded() -> None:
    container = _Container(wait_exc=RuntimeError("connection reset"))
    runner, db, *_ = _build([_gpu()], container)
    await runner.probe_gpu("gpu_1")
    assert db.rows["gpus"][0].probe_error == "probe failed while waiting for the container: connection reset"
    assert container.removed == [True]


async def test_container_that_cannot_start_is_recorded() -> None:
    runner, db, docker, *_ = _build([_gpu()])
    assert docker is not None
    docker.containers.run_exc = RuntimeError("image not found: " + "y" * 900)
    await runner.probe_gpu("gpu_1")
    error = db.rows["gpus"][0].probe_error
    assert error is not None
    assert error.startswith("probe container could not start: image not found")
    assert len(error) == 500


async def test_remove_failure_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    container = _Container(stdout=_payload(["h264"]))
    container.remove_exc = RuntimeError("already gone")
    runner, db, *_ = _build([_gpu()], container)
    with caplog.at_level("WARNING", logger="arm_backend.gpu_probe_runner"):
        await runner.probe_gpu("gpu_1")
    assert db.rows["gpus"][0].encoder_kinds == ["h264"]
    assert "already gone" in caplog.text


# --- row lifecycle races -----------------------------------------------------


async def test_row_deleted_mid_probe_writes_nothing() -> None:
    runner, db, docker, hub, dispatcher = _build([_gpu()])
    assert docker is not None
    docker.containers.on_run = lambda _kw: db.rows.__setitem__("gpus", [])

    await runner.probe_gpu("gpu_1")  # no exception

    assert db.rows["gpus"] == []
    assert db.added == []
    assert db.committed == 0
    assert hub.events == []
    assert dispatcher.probing_gpu_ids == set()


async def test_row_deleted_between_read_and_commit_writes_nothing() -> None:
    runner, db, _docker, hub, dispatcher = _build([_gpu()])
    db.commit_raises = StaleDataError("UPDATE statement on table 'gpus' expected to update 1 row(s); 0 were matched.")

    await runner.probe_gpu("gpu_1")  # no exception

    assert hub.events == []
    assert dispatcher.probing_gpu_ids == set()


async def test_row_disabled_mid_probe_still_gets_its_result() -> None:
    gpu = _gpu()
    runner, db, docker, hub, _d = _build([gpu])
    assert docker is not None

    def _disable(_kw: dict[str, Any]) -> None:
        gpu.enabled = False

    docker.containers.on_run = _disable
    await runner.probe_gpu("gpu_1")
    assert gpu.enabled is False
    assert gpu.encoder_kinds == ["h265"]
    assert gpu.probed_at is not None
    assert hub.events[0][1] == "gpu.probed"


async def test_unknown_row_is_a_no_op() -> None:
    runner, db, docker, hub, dispatcher = _build([])
    await runner.probe_gpu("gpu_missing")
    assert docker is not None and docker.containers.calls == []
    assert hub.events == []
    assert dispatcher.probing_gpu_ids == set()


async def test_busy_row_is_never_probed() -> None:
    runner, db, docker, hub, _d = _build([_gpu(status=GpuStatus.BUSY, claimed_by_task_id="tt_1")])
    await runner.probe_gpu("gpu_1")
    assert docker is not None and docker.containers.calls == []
    assert db.rows["gpus"][0].probed_at is None
    assert hub.events == []


async def test_uncommitted_claim_is_never_probed() -> None:
    # The claim has marked the row BUSY in its own session but not committed
    # yet: this session still reads AVAILABLE, the in-process marker decides.
    runner, db, docker, hub, dispatcher = _build([_gpu()])
    dispatcher.claimed_gpu_ids.add("gpu_1")
    assert runner.gpu_in_use(db.rows["gpus"][0]) is True
    assert runner.start_probe("gpu_1") is False
    await runner.probe_gpu("gpu_1")
    assert docker is not None and docker.containers.calls == []
    assert db.rows["gpus"][0].probed_at is None
    assert dispatcher.probing_gpu_ids == set()
    assert hub.events == []


async def test_claim_landing_after_reservation_stops_the_probe() -> None:
    runner, db, docker, hub, dispatcher = _build([_gpu()])
    assert runner.start_probe("gpu_1") is True
    dispatcher.claimed_gpu_ids.add("gpu_1")  # claimed before the task's first step
    await asyncio.gather(*runner.pending_tasks())
    assert docker is not None and docker.containers.calls == []
    assert hub.events == []


async def test_already_probing_row_is_not_probed_twice() -> None:
    runner, _db, docker, _hub, dispatcher = _build([_gpu()])
    dispatcher.probing_gpu_ids.add("gpu_1")
    await runner.probe_gpu("gpu_1")
    assert docker is not None and docker.containers.calls == []
    assert dispatcher.probing_gpu_ids == {"gpu_1"}  # the other probe still owns it


async def test_probe_without_docker_writes_nothing() -> None:
    runner, db, _docker, hub, _d = _build([_gpu()], docker=False)
    await runner.probe_gpu("gpu_1")
    assert db.rows["gpus"][0].probed_at is None
    assert hub.events == []


async def test_unexpected_error_is_logged_and_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    runner, db, _docker, _hub, dispatcher = _build([_gpu()])

    async def _boom(_stmt: Any) -> Any:
        raise RuntimeError("db down")

    db.execute = _boom  # type: ignore[method-assign]
    with caplog.at_level("ERROR", logger="arm_backend.gpu_probe_runner"):
        await runner.probe_gpu("gpu_1")
    assert "db down" in caplog.text
    assert dispatcher.probing_gpu_ids == set()


# --- spawn kwargs --------------------------------------------------------------


async def test_spawn_kwargs_for_a_qsv_row() -> None:
    checked: list[str] = []

    def _exists(image: str) -> bool:
        checked.append(image)
        return image == "arm-transcode:latest-intel"

    runner, _db, docker, *_ = _build(
        [_gpu(device_path="/dev/dri/renderD129")],
        image_exists=_exists,
        ARM_TRANSCODE_PUID="1001",
        ARM_TRANSCODE_PGID="1002",
        ARM_RENDER_GID="993",
        ARM_TRANSCODE_DOCKER_HOST="",
    )
    await runner.probe_gpu("gpu_1")

    assert docker is not None
    (kw,) = docker.containers.calls
    assert kw["image"] == "arm-transcode:latest-intel"
    assert checked == ["arm-transcode:latest-intel"]
    assert kw["command"] == ["python", "-m", "arm_transcode.main", "--probe-device"]
    assert kw["environment"] == {
        "ARM_GPU_VENDOR": "qsv",
        "ARM_GPU_DEVICE": "/dev/dri/renderD129",
        "ARM_LOG_LEVEL": "info",
        "PUID": "1001",
        "PGID": "1002",
        "RENDER_GID": "993",
    }
    assert kw["devices"] == ["/dev/dri/renderD129:/dev/dri/renderD129:rwm"]
    assert "volumes" not in kw
    assert kw["network"] is None
    assert kw["detach"] is True
    assert kw["auto_remove"] is False
    assert kw["labels"] == {"arm.gpu_probe": "gpu_1"}


async def test_spawn_kwargs_for_an_nvenc_row() -> None:
    runner, _db, docker, *_ = _build(
        [_gpu(vendor=GpuVendor.NVENC, device_path="nvidia://1")],
        ARM_RENDER_GID="993",
        ARM_TRANSCODE_IMAGE_NVENC="arm-transcode:cuda",
    )
    await runner.probe_gpu("gpu_1")
    assert docker is not None
    (kw,) = docker.containers.calls
    assert kw["image"] == "arm-transcode:cuda"
    assert kw["environment"] == {"ARM_GPU_VENDOR": "nvenc", "ARM_GPU_DEVICE": "nvidia://1", "ARM_LOG_LEVEL": "info"}
    assert kw["runtime"] == "nvidia"
    assert len(kw["device_requests"]) == 1
    assert "devices" not in kw


# --- boot pass -------------------------------------------------------------------


async def test_boot_pass_probes_enabled_unprobed_or_unverified_rows_sequentially() -> None:
    probed = datetime(2026, 9, 1, tzinfo=UTC)
    rows = [
        _gpu("gpu_a"),
        _gpu("gpu_b", probed_at=probed, encoder_kinds=["h264"]),
        _gpu("gpu_c", enabled=False),
        _gpu("gpu_d", GpuVendor.VAAPI, device_path="/dev/dri/renderD129", probed_at=probed, probe_error="failed"),
        _gpu("gpu_e", enabled=False, probed_at=probed),
    ]
    runner, db, docker, hub, dispatcher = _build(rows)
    assert docker is not None
    concurrent: list[set[str]] = []
    docker.containers.on_run = lambda _kw: concurrent.append(set(dispatcher.probing_gpu_ids))

    await runner.probe_unprobed()

    assert [kw["environment"]["ARM_GPU_DEVICE"] for kw in docker.containers.calls] == [
        "/dev/dri/renderD128",
        "/dev/dri/renderD129",
    ]
    assert concurrent == [{"gpu_a"}, {"gpu_d"}]  # one at a time
    assert [e[2]["gpu_id"] for e in hub.events] == ["gpu_a", "gpu_d"]
    by_id = {g.id: g for g in db.rows["gpus"]}
    assert by_id["gpu_b"].probed_at == probed
    assert by_id["gpu_c"].probed_at is None
    assert by_id["gpu_d"].encoder_kinds == ["h265"]  # a failed row is retried at boot
    assert by_id["gpu_e"].probed_at == probed


async def test_boot_pass_with_every_row_probed_spawns_nothing() -> None:
    runner, _db, docker, hub, _d = _build([_gpu(probed_at=datetime(2026, 9, 1, tzinfo=UTC), encoder_kinds=["h264"])])
    await runner.probe_unprobed()
    assert docker is not None and docker.containers.calls == []
    assert hub.events == []


async def test_boot_pass_is_a_no_op_without_docker() -> None:
    runner, db, _docker, hub, _d = _build([_gpu()], docker=False)
    await runner.probe_unprobed()
    assert db.rows["gpus"][0].probed_at is None
    assert hub.events == []


async def test_boot_pass_is_a_no_op_when_not_capable() -> None:
    runner, _db, docker, hub, _d = _build([_gpu()], ARM_TRANSCODE_CAPABLE=False)
    assert runner.capable() is False
    await runner.probe_unprobed()
    assert docker is not None and docker.containers.calls == []


async def test_remote_docker_host_implies_capable() -> None:
    runner, *_ = _build([], ARM_TRANSCODE_CAPABLE=False, ARM_TRANSCODE_DOCKER_HOST="ssh://gpu-host")
    assert runner.capable() is True


async def test_boot_pass_survives_a_db_error(caplog: pytest.LogCaptureFixture) -> None:
    runner, db, *_ = _build([_gpu()])

    async def _boom(_stmt: Any) -> Any:
        raise RuntimeError("db down")

    db.execute = _boom  # type: ignore[method-assign]
    with caplog.at_level("ERROR", logger="arm_backend.gpu_probe_runner"):
        await runner.probe_unprobed()
    assert "db down" in caplog.text


# --- background scheduling -----------------------------------------------------


async def test_start_probe_schedules_once_and_releases() -> None:
    runner, db, docker, _hub, dispatcher = _build([_gpu()])

    assert runner.start_probe("gpu_1") is True
    assert "gpu_1" in dispatcher.probing_gpu_ids  # reserved before the task runs
    assert runner.start_probe("gpu_1") is False

    await asyncio.gather(*runner.pending_tasks())
    assert docker is not None and len(docker.containers.calls) == 1
    assert db.rows["gpus"][0].encoder_kinds == ["h265"]
    assert dispatcher.probing_gpu_ids == set()
    assert runner.pending_tasks() == []


async def test_shutdown_before_a_probe_starts_releases_reservations() -> None:
    runner, _db, docker, _hub, dispatcher = _build([_gpu()])
    assert runner.start_probe("gpu_1") is True
    tasks = runner.pending_tasks()
    await runner.shutdown()
    assert all(t.cancelled() for t in tasks)
    assert dispatcher.probing_gpu_ids == set()
    assert docker is not None and docker.containers.calls == []


async def test_shutdown_removes_the_container_of_a_running_probe() -> None:
    gate = threading.Event()
    waiting = threading.Event()

    def _blocking_wait(timeout: object = None) -> dict[str, int]:
        waiting.set()
        gate.wait(5)
        return {"StatusCode": 0}

    container = _Container(stdout=_payload(["h265"]))
    container.wait = _blocking_wait  # type: ignore[method-assign]
    runner, db, _docker, hub, dispatcher = _build([_gpu()], container)
    assert runner.start_probe("gpu_1") is True
    try:
        assert await asyncio.to_thread(waiting.wait, 5)
        await runner.shutdown()
    finally:
        gate.set()
    assert container.removed == [True]
    assert db.rows["gpus"][0].probed_at is None  # cancelled: nothing written
    assert hub.events == []
    assert dispatcher.probing_gpu_ids == set()
    assert runner.pending_tasks() == []


async def test_shutdown_with_nothing_pending_returns() -> None:
    runner, *_ = _build([])
    await runner.shutdown()


async def test_start_boot_pass_runs_in_the_background() -> None:
    runner, db, *_ = _build([_gpu()])
    task = runner.start_boot_pass()
    assert runner.pending_tasks() == [task]
    await task
    assert db.rows["gpus"][0].encoder_kinds == ["h265"]
    await asyncio.sleep(0)  # let the done-callback run
    assert runner.pending_tasks() == []


# --- orphaned probe containers ---------------------------------------------------


async def test_boot_pass_removes_orphaned_probe_containers_first() -> None:
    runner, _db, docker, _hub, dispatcher = _build(
        [_gpu(probed_at=datetime(2026, 9, 1, tzinfo=UTC), encoder_kinds=["h264"])]
    )
    assert docker is not None
    orphan = _Container(labels={"arm.gpu_probe": "gpu_old"})
    unlabeled = _Container()
    live = _Container(labels={"arm.gpu_probe": "gpu_live"})
    docker.containers.existing = [orphan, unlabeled, live]
    dispatcher.probing_gpu_ids.add("gpu_live")  # a probe running right now keeps its container

    await runner.probe_unprobed()

    assert docker.containers.list_calls == [{"all": True, "filters": {"label": "arm.gpu_probe"}}]
    assert orphan.removed == [True]
    assert unlabeled.removed == [True]
    assert live.removed == []


async def test_orphan_cleanup_failures_never_raise(caplog: pytest.LogCaptureFixture) -> None:
    runner, _db, docker, *_ = _build([])
    assert docker is not None
    stuck = _Container(labels={"arm.gpu_probe": "gpu_old"})
    stuck.remove_exc = RuntimeError("removal in progress")
    docker.containers.existing = [stuck]
    with caplog.at_level("WARNING", logger="arm_backend.gpu_probe_runner"):
        assert await runner.remove_orphans() == 0
    assert "removal in progress" in caplog.text

    docker.containers.list_exc = RuntimeError("daemon unreachable")
    with caplog.at_level("WARNING", logger="arm_backend.gpu_probe_runner"):
        assert await runner.remove_orphans() == 0
    assert "daemon unreachable" in caplog.text


async def test_orphan_cleanup_without_docker_is_a_no_op() -> None:
    runner, *_ = _build([], docker=False)
    assert await runner.remove_orphans() == 0


def test_timeout_constant() -> None:
    assert runner_mod.PROBE_TIMEOUT_S == 120
