"""Characterization tests for arm_ripper.main startup: amain, the keycheck loop,
heartbeat error handling and run_source_mode cancellation."""

import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

import asyncio  # noqa: E402
import logging  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from arm_ripper import main  # noqa: E402
from arm_ripper.drive_handle import DriveHandle  # noqa: E402


class _Stop(Exception):
    """Private sentinel used to break out of the endless loops."""


# --------------------------------------------------------------------------- amain


class _Rig:
    """Records everything amain touches."""

    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.controller_kwargs: dict = {}
        self.controller_args: tuple = ()
        self.subscribed: list[tuple] = []
        self.ws_kwargs: dict = {}
        self.register_args: tuple = ()
        self.started: set[str] = set()
        self.cancelled: set[str] = set()
        self.client = None
        self.controller = None
        self.handle: DriveHandle | None = None


def _install(monkeypatch, *, source=None, drive_dev="/dev/sr0", resolved="unset", mode_exc=None, probe_exc=None):
    rig = _Rig()
    monkeypatch.setattr(main.settings, "ARM_SOURCE_PATH", source)
    monkeypatch.setattr(main.settings, "ARM_DRIVE_DEV", drive_dev)
    monkeypatch.setattr(main.settings, "ARM_DRIVE_BY_ID", "by-id-x")
    monkeypatch.setattr(main.settings, "ARM_SOURCE_SESSION_ID", "sess_9")
    monkeypatch.setattr(main.settings, "ARM_BACKEND_URL", "https://backend.example")
    monkeypatch.setattr(main.settings, "ARM_SERVICE_TOKEN", "tok")
    monkeypatch.setattr(main.settings, "ARM_DRIVE_ID", "drv_cfg")
    monkeypatch.setattr(main.settings, "HOSTNAME", "host1")
    monkeypatch.setattr(main.settings, "ARM_MIN_LENGTH_SECONDS", 77)

    class FakeClient:
        def __init__(self, *a, **kw) -> None:
            rig.client = self
            rig.client_args = (a, kw)
            self.closed = False

        async def close(self) -> None:
            self.closed = True
            rig.events.append(("close",))

    class FakeWS:
        def __init__(self, url, token, **kw) -> None:
            rig.ws_kwargs = {"url": url, "token": token, **kw}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            rig.events.append(("ws_exit",))

        async def subscribe(self, topic, cb) -> None:
            rig.subscribed.append((topic, cb))

    class FakeController:
        def __init__(self, *args, **kwargs) -> None:
            rig.controller = self
            rig.controller_args = args
            rig.controller_kwargs = kwargs

        async def on_ws_command(self, msg) -> None:  # pragma: no cover - never invoked
            pass

    async def register(client, device_path):
        rig.register_args = (client, device_path)
        return "drv_reg"

    async def boot(client, drive_id, path, controller):
        rig.events.append(("boot", client, drive_id, path, controller))
        if probe_exc:
            raise probe_exc

    def _forever(name):
        async def loop(*a, **kw):
            rig.started.add(name)
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                rig.cancelled.add(name)
                raise

        return loop

    async def run_source(controller, session_id):
        rig.events.append(("run_source", controller, session_id))
        await asyncio.sleep(0)
        assert rig.started == {"hb", "key"}
        if mode_exc:
            raise mode_exc

    async def poll(controller, handle, *, client, drive_id):
        rig.events.append(("poll", controller, handle, client, drive_id))
        rig.handle = handle
        await asyncio.sleep(0)
        assert rig.started == {"hb", "key"}
        if mode_exc:
            raise mode_exc

    def resolve(by_id, dev, **kw):
        rig.events.append(("resolve", by_id, dev))
        return None if resolved is None else SimpleNamespace(path="/dev/sr3", via="by-id")

    monkeypatch.setattr(main, "BackendClient", FakeClient)
    monkeypatch.setattr(main.ssl, "create_default_context", lambda cafile=None: ("ctx", cafile))
    monkeypatch.setattr(main, "WSClient", FakeWS)
    monkeypatch.setattr(main, "register_with_retry", register)
    monkeypatch.setattr(main, "JobController", FakeController)
    monkeypatch.setattr(main, "boot_probe", boot)
    monkeypatch.setattr(main, "heartbeat_loop", _forever("hb"))
    monkeypatch.setattr(main, "makemkv_keycheck_loop", _forever("key"))
    monkeypatch.setattr(main, "run_source_mode", run_source)
    monkeypatch.setattr(main, "poll_loop", poll)
    monkeypatch.setattr(main, "resolve_drive_device", resolve)
    monkeypatch.setattr(main.prepare, "configure", lambda c, d: rig.events.append(("configure", c, d)))
    return rig


def _names(rig):
    return [e[0] for e in rig.events]


def test_build_client_passes_url_token_hostname_and_drive_id(monkeypatch) -> None:
    calls = []
    built = object()

    def recorder(*args, **kwargs):
        calls.append((args, kwargs))
        return built

    monkeypatch.setattr(main, "BackendClient", recorder)
    monkeypatch.setattr(main.settings, "ARM_BACKEND_URL", "https://backend.test")
    monkeypatch.setattr(main.settings, "ARM_SERVICE_TOKEN", "tok")
    monkeypatch.setattr(main.settings, "HOSTNAME", "host-1")
    monkeypatch.setattr(main.settings, "ARM_DRIVE_ID", "drive-1")

    assert main._build_client() is built
    assert calls == [(("https://backend.test", "tok"), {"hostname": "host-1", "drive_id": "drive-1"})]


def _stub_resolve(monkeypatch, result):
    calls = []

    def resolve(by_id, dev, **kw):
        calls.append((by_id, dev, kw))
        return result

    monkeypatch.setattr(main, "resolve_drive_device", resolve)
    monkeypatch.setattr(main, "_resolve_paths", lambda: {"sysfs_root": "/sys-x"})
    return calls


def test_initial_handle_source_path_is_fixed_and_never_resolves(monkeypatch) -> None:
    calls = _stub_resolve(monkeypatch, None)
    handle = main._initial_handle("/data/x.iso")
    assert handle.current == "/data/x.iso"
    assert calls == []


def test_initial_handle_resolved_drive_logs_presence(monkeypatch, caplog) -> None:
    _stub_resolve(monkeypatch, SimpleNamespace(path="/dev/sr3", via="by-id"))
    with caplog.at_level(logging.INFO, logger="arm_ripper"):
        handle = main._initial_handle(None)
    assert handle.current == "/dev/sr3"
    assert "drive present at /dev/sr3 via by-id" in caplog.messages
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_initial_handle_unresolved_drive_is_absent_and_warns(monkeypatch, caplog) -> None:
    _stub_resolve(monkeypatch, None)
    monkeypatch.setattr(main.settings, "ARM_DRIVE_BY_ID", "by-id-x")
    with caplog.at_level(logging.INFO, logger="arm_ripper"):
        handle = main._initial_handle(None)
    assert handle.absent
    assert "starting with the drive absent (by_id=by-id-x); will poll for it" in caplog.messages


def test_initial_handle_passes_settings_and_paths_with_empty_dev_fallback(monkeypatch) -> None:
    calls = _stub_resolve(monkeypatch, None)
    monkeypatch.setattr(main.settings, "ARM_DRIVE_BY_ID", "by-id-x")
    monkeypatch.setattr(main.settings, "ARM_DRIVE_DEV", None)
    main._initial_handle(None)
    assert calls == [("by-id-x", "", {"sysfs_root": "/sys-x"})]
    monkeypatch.setattr(main.settings, "ARM_DRIVE_DEV", "/dev/sr0")
    main._initial_handle(None)
    assert calls[1] == ("by-id-x", "/dev/sr0", {"sysfs_root": "/sys-x"})


def _record_controller(monkeypatch):
    calls = []
    built = object()

    def recorder(*args, **kwargs):
        calls.append((args, kwargs))
        return built

    monkeypatch.setattr(main, "JobController", recorder)
    monkeypatch.setattr(main.settings, "ARM_MIN_LENGTH_SECONDS", 77)
    return calls, built


def test_build_controller_source_mode_never_times_out_resolution(monkeypatch) -> None:
    calls, built = _record_controller(monkeypatch)
    handle, ws, client = DriveHandle.fixed("/data/x.iso"), object(), object()
    assert main._build_controller(client, "drv_1", ws, handle, source_mode=True) is built
    assert calls == [
        (
            (client, "drv_1"),
            {"ws": ws, "device_path": handle, "default_min_length_seconds": 77, "resolution_timeout": None},
        )
    ]


def test_build_controller_drive_mode_leaves_resolution_timeout_to_the_default(monkeypatch) -> None:
    calls, built = _record_controller(monkeypatch)
    handle, ws, client = DriveHandle("/dev/sr0"), object(), object()
    assert main._build_controller(client, "drv_1", ws, handle, source_mode=False) is built
    assert calls == [((client, "drv_1"), {"ws": ws, "device_path": handle, "default_min_length_seconds": 77})]
    assert "resolution_timeout" not in calls[0][1]


async def test_recover_crashed_rip_probes_the_current_node(monkeypatch) -> None:
    calls = []

    async def probe(*args):
        calls.append(args)

    monkeypatch.setattr(main, "boot_probe", probe)
    client, controller = object(), object()
    await main._recover_crashed_rip(client, "drv_1", DriveHandle("/dev/sr0"), controller)
    assert calls == [(client, "drv_1", "/dev/sr0", controller)]


async def test_recover_crashed_rip_swallows_and_logs_probe_errors(monkeypatch, caplog) -> None:
    async def probe(*args):
        raise RuntimeError("probe broke")

    monkeypatch.setattr(main, "boot_probe", probe)
    with caplog.at_level(logging.ERROR, logger="arm_ripper"):
        await main._recover_crashed_rip(object(), "drv_1", DriveHandle("/dev/sr0"), object())
    assert "boot probe failed: probe broke" in caplog.messages


def _record_modes(monkeypatch):
    calls = []

    async def run_source(*args):
        calls.append(("run_source_mode", args))

    async def poll(*args, **kwargs):
        calls.append(("poll_loop", args, kwargs))

    monkeypatch.setattr(main, "run_source_mode", run_source)
    monkeypatch.setattr(main, "poll_loop", poll)
    return calls


async def test_run_mode_source_mode_runs_the_one_shot_pipeline(monkeypatch, caplog) -> None:
    calls = _record_modes(monkeypatch)
    monkeypatch.setattr(main.settings, "ARM_SOURCE_SESSION_ID", "sess_9")
    controller, client = object(), object()
    with caplog.at_level(logging.INFO, logger="arm_ripper"):
        await main._run_mode(
            controller, DriveHandle.fixed("/data/x.iso"), client=client, drive_id="d", source_mode=True
        )
    assert calls == [("run_source_mode", (controller, "sess_9"))]
    assert caplog.messages == [
        "ARM_SOURCE_PATH=/data/x.iso; running one-shot pipeline",
        "source pipeline complete; exiting",
    ]


async def test_run_mode_drive_mode_polls_the_drive(monkeypatch, caplog) -> None:
    calls = _record_modes(monkeypatch)
    controller, client, handle = object(), object(), DriveHandle("/dev/sr0")
    with caplog.at_level(logging.INFO, logger="arm_ripper"):
        await main._run_mode(controller, handle, client=client, drive_id="d", source_mode=False)
    assert calls == [("poll_loop", (controller, handle), {"client": client, "drive_id": "d"})]
    assert caplog.messages == []


async def test_amain_exits_2_when_nothing_to_rip_and_never_closes_client(monkeypatch, caplog) -> None:
    rig = _install(monkeypatch, source=None, drive_dev=None)
    with caplog.at_level(logging.ERROR, logger="arm_ripper"), pytest.raises(SystemExit) as ei:
        await main.amain()
    assert ei.value.code == 2
    assert "neither ARM_SOURCE_PATH nor ARM_DRIVE_DEV is set; nothing to rip" in caplog.messages
    # Quirk: the client is built before the check but the try/finally starts after it.
    assert rig.client is not None
    assert rig.client.closed is False
    assert rig.register_args == ()


async def test_amain_source_mode(monkeypatch, caplog) -> None:
    rig = _install(monkeypatch, source="/data/x.iso", drive_dev=None)
    with caplog.at_level(logging.INFO, logger="arm_ripper"):
        await main.amain()
    await asyncio.sleep(0)
    assert rig.register_args == (rig.client, "/data/x.iso")
    assert rig.controller_args == (rig.client, "drv_reg")
    kw = rig.controller_kwargs
    assert kw["resolution_timeout"] is None
    assert kw["default_min_length_seconds"] == 77
    assert kw["ws"] is not None
    assert kw["device_path"].current == "/data/x.iso"
    assert rig.ws_kwargs["url"] == "wss://backend.example/ws"
    assert rig.ws_kwargs["ssl_context"] == ("ctx", main.CA_BUNDLE_PATH)
    assert rig.subscribed == [("ripper.commands.drv_reg", rig.controller.on_ws_command)]
    assert _names(rig) == ["configure", "run_source", "ws_exit", "close"]
    assert rig.events[0][1:] == (rig.client, "drv_reg")
    assert rig.events[1][1:] == (rig.controller, "sess_9")
    assert "ARM_SOURCE_PATH=/data/x.iso; running one-shot pipeline" in caplog.messages
    assert "source pipeline complete; exiting" in caplog.messages
    assert rig.cancelled == {"hb", "key"}
    assert rig.client.closed


async def test_amain_drive_present(monkeypatch, caplog) -> None:
    rig = _install(monkeypatch)
    with caplog.at_level(logging.INFO, logger="arm_ripper"):
        await main.amain()
    await asyncio.sleep(0)
    assert "drive present at /dev/sr3 via by-id" in caplog.messages
    assert rig.register_args == (rig.client, "/dev/sr3")
    assert "resolution_timeout" not in rig.controller_kwargs
    assert rig.controller_kwargs["default_min_length_seconds"] == 77
    assert _names(rig) == ["resolve", "boot", "poll", "ws_exit", "close"]
    assert rig.events[0][1:] == ("by-id-x", "/dev/sr0")
    assert rig.events[1][1:] == (rig.client, "drv_reg", "/dev/sr3", rig.controller)
    assert rig.events[2][1:] == (rig.controller, rig.handle, rig.client, "drv_reg")
    assert rig.subscribed == [("ripper.commands.drv_reg", rig.controller.on_ws_command)]
    assert "ARM_SOURCE_PATH" not in " ".join(caplog.messages)
    assert rig.cancelled == {"hb", "key"}


async def test_amain_drive_absent_skips_boot_probe_but_polls(monkeypatch, caplog) -> None:
    rig = _install(monkeypatch, resolved=None)
    with caplog.at_level(logging.WARNING, logger="arm_ripper"):
        await main.amain()
    await asyncio.sleep(0)
    assert "starting with the drive absent (by_id=by-id-x); will poll for it" in caplog.messages
    assert rig.register_args == (rig.client, "/dev/sr0")
    assert _names(rig) == ["resolve", "poll", "ws_exit", "close"]
    assert rig.handle is not None and rig.handle.absent
    assert rig.cancelled == {"hb", "key"}


async def test_amain_boot_probe_failure_is_logged_and_boot_continues(monkeypatch, caplog) -> None:
    rig = _install(monkeypatch, probe_exc=RuntimeError("kaput"))
    with caplog.at_level(logging.ERROR, logger="arm_ripper"):
        await main.amain()
    await asyncio.sleep(0)
    assert "boot probe failed: kaput" in caplog.messages
    assert _names(rig) == ["resolve", "boot", "poll", "ws_exit", "close"]


@pytest.mark.parametrize("source", [None, "/data/x.iso"])
async def test_amain_cancels_tasks_and_closes_client_when_mode_raises(monkeypatch, source) -> None:
    rig = _install(monkeypatch, source=source, drive_dev=None if source else "/dev/sr0", mode_exc=_Stop())
    with pytest.raises(_Stop):
        await main.amain()
    await asyncio.sleep(0)
    assert rig.cancelled == {"hb", "key"}
    assert rig.client.closed
    assert _names(rig)[-2:] == ["ws_exit", "close"]


# ---------------------------------------------------------------- makemkv_keycheck_loop


class _KeyClient:
    def __init__(self, items) -> None:
        self.items = list(items)
        self.reports: list[tuple] = []

    async def get_ripper_config(self):
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return SimpleNamespace(makemkv_key=item)

    async def report_makemkv_key_status(self, *, state, detail) -> None:
        self.reports.append((state, detail))


async def _run_keycheck(monkeypatch, items, *, probe_exc_on=None):
    client = _KeyClient(items)
    refreshed: list[str | None] = []
    probed: list[str | None] = []
    n = {"sleeps": 0}

    async def refresh(*, key):
        refreshed.append(key)

    async def probe(key):
        probed.append(key)
        if probe_exc_on == len(probed):
            raise ValueError("probe boom")
        return ("valid", f"d{len(probed)}")

    async def sleep(_s):
        n["sleeps"] += 1
        if n["sleeps"] >= len(items):
            raise _Stop

    monkeypatch.setattr(main, "refresh_makemkv_key", refresh)
    monkeypatch.setattr(main, "probe_makemkv_key", probe)
    monkeypatch.setattr(main.asyncio, "sleep", sleep)
    with pytest.raises(_Stop):
        await main.makemkv_keycheck_loop(client)  # type: ignore[arg-type]
    return client, refreshed, probed


def _record_key_pass(monkeypatch):
    events: list[tuple] = []

    async def refresh(*, key):
        events.append(("refresh", key))

    async def probe(key):
        events.append(("probe", key))
        return ("valid", "detail")

    monkeypatch.setattr(main, "refresh_makemkv_key", refresh)
    monkeypatch.setattr(main, "probe_makemkv_key", probe)
    return events


class _RecordingKeyClient(_KeyClient):
    def __init__(self, items, events) -> None:
        super().__init__(items)
        self.events = events

    async def report_makemkv_key_status(self, *, state, detail) -> None:
        self.events.append(("report", state, detail))


async def test_check_makemkv_key_first_pass_refreshes_then_probes_and_reports(monkeypatch) -> None:
    events = _record_key_pass(monkeypatch)
    client = _RecordingKeyClient(["K"], events)
    returned = await main._check_makemkv_key(client, last_key=None, first=True)  # type: ignore[arg-type]
    assert returned == "K"
    assert events == [("refresh", "K"), ("probe", "K"), ("report", "valid", "detail")]


async def test_check_makemkv_key_unchanged_key_skips_refresh_but_probes_and_reports(monkeypatch) -> None:
    events = _record_key_pass(monkeypatch)
    client = _RecordingKeyClient(["K"], events)
    returned = await main._check_makemkv_key(client, last_key="K", first=False)  # type: ignore[arg-type]
    assert returned == "K"
    assert events == [("probe", "K"), ("report", "valid", "detail")]


async def test_check_makemkv_key_changed_key_refreshes(monkeypatch) -> None:
    events = _record_key_pass(monkeypatch)
    client = _RecordingKeyClient(["K2"], events)
    returned = await main._check_makemkv_key(client, last_key="K1", first=False)  # type: ignore[arg-type]
    assert returned == "K2"
    assert events[0] == ("refresh", "K2")


async def test_check_makemkv_key_config_error_propagates_before_any_step(monkeypatch) -> None:
    events = _record_key_pass(monkeypatch)
    client = _RecordingKeyClient([httpx.ConnectError("down")], events)
    with pytest.raises(httpx.ConnectError):
        await main._check_makemkv_key(client, last_key=None, first=True)  # type: ignore[arg-type]
    assert events == []


async def test_keycheck_first_pass_refreshes_and_unchanged_key_does_not(monkeypatch) -> None:
    client, refreshed, probed = await _run_keycheck(monkeypatch, ["K", "K", "K"])
    assert refreshed == ["K"]
    assert probed == ["K", "K", "K"]
    assert client.reports == [("valid", "d1"), ("valid", "d2"), ("valid", "d3")]


async def test_keycheck_changed_key_refreshes(monkeypatch) -> None:
    _, refreshed, _ = await _run_keycheck(monkeypatch, ["A", "B", "B"])
    assert refreshed == ["A", "B"]


async def test_keycheck_blank_and_none_are_the_same_key(monkeypatch) -> None:
    _, refreshed, _ = await _run_keycheck(monkeypatch, [None, "  ", "", None])
    assert refreshed == [None]


async def test_keycheck_http_and_os_errors_warn_and_loop_continues(monkeypatch, caplog) -> None:
    items = [httpx.ConnectError("down"), OSError("io"), "K"]
    with caplog.at_level(logging.WARNING, logger="arm_ripper"):
        client, refreshed, _ = await _run_keycheck(monkeypatch, items)
    assert "makemkv keycheck failed: down" in caplog.messages
    assert "makemkv keycheck failed: io" in caplog.messages
    assert client.reports == [("valid", "d1")]
    assert refreshed == ["K"]


async def test_keycheck_unexpected_error_is_logged_and_loop_continues(monkeypatch, caplog) -> None:
    with caplog.at_level(logging.ERROR, logger="arm_ripper"):
        client, refreshed, _ = await _run_keycheck(monkeypatch, ["K", "K"], probe_exc_on=1)
    rec = [r for r in caplog.records if r.message == "makemkv keycheck: unexpected error"]
    assert len(rec) == 1 and rec[0].exc_info is not None
    # The failed first pass leaves first=True, so the next pass refreshes again.
    assert refreshed == ["K", "K"]
    assert client.reports == [("valid", "d2")]


async def test_keycheck_failed_first_pass_still_counts_as_first(monkeypatch) -> None:
    _, refreshed, _ = await _run_keycheck(monkeypatch, [OSError("x"), "K", "K"])
    assert refreshed == ["K"]
    # fail, then "first" pass refreshes; third pass (unchanged) does not
    _, refreshed, _ = await _run_keycheck(monkeypatch, ["K", OSError("x"), "K"])
    assert refreshed == ["K"]


# ------------------------------------------------------------------ heartbeat errors


@pytest.mark.parametrize("exc", [httpx.ConnectError("net down"), OSError("sock gone")])
async def test_heartbeat_error_warns_and_keeps_beating(monkeypatch, caplog, exc) -> None:
    calls = {"n": 0}

    class Client:
        async def heartbeat(self, *, drive_id, media_status) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise exc

        async def get_current_job(self, drive_id):  # pragma: no cover - not reached
            return None

    class Ctl:
        def is_idle(self) -> bool:  # pragma: no cover - not reached
            return False

    async def sleep(_s):
        if calls["n"] >= 2:
            raise _Stop

    monkeypatch.setattr(main.asyncio, "sleep", sleep)
    monkeypatch.setattr(main, "probe_drive_media", lambda p: (main.DriveMediaStatus.NO_DISC, "f"))
    with caplog.at_level(logging.WARNING, logger="arm_ripper"), pytest.raises(_Stop):
        await main.heartbeat_loop(Client(), "drv", DriveHandle("/dev/sr0"), Ctl())  # type: ignore[arg-type]
    assert f"heartbeat failed: {exc}" in caplog.messages
    assert calls["n"] == 2


# ------------------------------------------------------------- run_source_mode cancel


class _BlockedController:
    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.inner: asyncio.Task | None = None

    async def handle_manual_trigger(self, session_id) -> None:
        self.inner = asyncio.current_task()
        await self.release.wait()


async def _spin() -> None:
    for _ in range(3):
        await asyncio.sleep(0)


async def test_cancelling_outer_while_inner_blocked_cancels_inner_and_returns(monkeypatch) -> None:
    discarded: list[bool] = []

    async def discard() -> None:
        discarded.append(True)

    monkeypatch.setattr(main.iso_extract, "discard_all", discard)
    ctl = _BlockedController()
    outer = asyncio.create_task(main.run_source_mode(ctl, None))  # type: ignore[arg-type]
    await _spin()
    outer.cancel()
    await asyncio.wait([outer], timeout=0.1)
    # Quirk: awaiting the inner task propagates the cancel into it, so the inner
    # ends up cancelled and run_source_mode swallows the error and returns normally.
    assert ctl.inner is not None and ctl.inner.cancelled()
    assert outer.done() and not outer.cancelled() and outer.exception() is None
    assert discarded == [True]


async def test_cancel_landing_after_inner_finished_propagates(monkeypatch) -> None:
    discarded: list[bool] = []

    async def discard() -> None:
        discarded.append(True)

    monkeypatch.setattr(main.iso_extract, "discard_all", discard)
    ctl = _BlockedController()
    outer = asyncio.create_task(main.run_source_mode(ctl, None))  # type: ignore[arg-type]
    await _spin()
    ctl.release.set()
    await asyncio.sleep(0)  # inner finishes; the outer wake-up is queued but not yet run
    assert ctl.inner is not None and ctl.inner.done()
    outer.cancel()
    await asyncio.wait([outer], timeout=0.1)
    assert outer.cancelled()
    assert not ctl.inner.cancelled()
    assert discarded == [True]
