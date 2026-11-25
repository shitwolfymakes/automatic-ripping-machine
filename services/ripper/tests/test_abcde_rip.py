"""End-to-end exercise of `rip_cd` against a faked abcde subprocess.

The fake replaces `asyncio.create_subprocess_exec` with a stub process.
As abcde 2.9.3 does, the test drops each `trackNN.wav` into the output
directory and then appends `movetrack-NN` to abcde's status file
(`abcde.<discid>/status`); `rip_cd` polls that file and fires its
`on_track_done` callback. Covers:

  - Live reporting: each track is reported as abcde moves it, while
    abcde is still running.
  - Happy path: each callback fires once, in track order, with a
    populated RipResult (size + sha256).
  - Late move: a WAV that lands after the last poll is caught by the
    post-exit sweep.
  - abcde executable missing: synthetic FileNotFoundError → every
    requested track gets a failure callback.
  - abcde exits non-zero: any track that didn't already succeed gets a
    failure with the stderr tail in the error message.
  - Total-rip timeout: abcde hangs past the wait_for budget → every
    unfinalised track gets a timeout failure.
  - on_track_done=None: no callback fires; the return dict still has an
    entry per requested track.
  - Kill path: abcde runs in its own session and the whole process group
    is killed, so cdparanoia does not outlive an abandon or timeout.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

import pytest

import arm_ripper.rip.abcde_rip as abcde_rip
from arm_ripper.rip.abcde_rip import rip_cd
from arm_ripper.rip.result import RipResult


_FAKE_PID = 424242


@pytest.fixture(autouse=True)
def killpg_calls(monkeypatch) -> list[tuple[int, int]]:
    """Record os.killpg instead of signalling a real process group."""
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(abcde_rip.os, "killpg", lambda pgid, sig: calls.append((pgid, sig)))
    return calls


class _FakeStream:
    """Async-readable stream emitting canned bytes lines, optionally
    invoking a hook before each readline so the test can mutate the FS
    in lock-step with abcde's output."""

    def __init__(self, lines: list[bytes], on_each_read: Any = None) -> None:
        self._lines = list(lines)
        self._on_each_read = on_each_read

    async def readline(self) -> bytes:
        if self._on_each_read is not None:
            self._on_each_read()
        if not self._lines:
            return b""
        return self._lines.pop(0)


class _FakeProc:
    def __init__(
        self,
        stdout_lines: list[bytes],
        stderr_lines: list[bytes] | None = None,
        returncode: int = 0,
        on_each_stdout_read: Any = None,
    ) -> None:
        self.stdout = _FakeStream(stdout_lines, on_each_read=on_each_stdout_read)
        self.stderr = _FakeStream(stderr_lines or [])
        self.returncode: int | None = None
        self._final_returncode = returncode
        self.pid = _FAKE_PID

    async def wait(self) -> int:
        await asyncio.sleep(0)
        if self.returncode is None:
            self.returncode = self._final_returncode
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


def _stub_subprocess(
    monkeypatch,
    lines: list[str],
    *,
    returncode: int = 0,
    stderr_lines: list[str] | None = None,
    on_each_stdout_read: Any = None,
) -> _FakeProc:
    encoded = [(line + "\n").encode() for line in lines]
    encoded_err = [(line + "\n").encode() for line in (stderr_lines or [])]
    fake = _FakeProc(
        encoded,
        stderr_lines=encoded_err,
        returncode=returncode,
        on_each_stdout_read=on_each_stdout_read,
    )

    async def fake_create_subprocess_exec(*_args: Any, **_kwargs: Any) -> _FakeProc:
        return fake

    monkeypatch.setattr(abcde_rip.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    return fake


def _write_track_wav(output_dir: Path, idx: int, payload: bytes | None = None) -> Path:
    p = output_dir / f"track{idx:02d}.wav"
    p.write_bytes(payload if payload is not None else b"RIFF" + bytes([idx]) * 32)
    return p


class _RunningProc(_FakeProc):
    """abcde mid-rip: stdout stays open, with nothing on it, until the test lets the process exit."""

    def __init__(self, exit_now: asyncio.Event) -> None:
        super().__init__([])
        self.stdout = self  # type: ignore[assignment]
        self._exit_now = exit_now

    async def readline(self) -> bytes:
        await self._exit_now.wait()
        return b""


def _append_status(output_dir: Path, *lines: str) -> None:
    """Append lines to abcde's status file in its work dir, as abcde 2.9.3 does after each step."""
    workdir = output_dir / "abcde.fc110d12"
    workdir.mkdir(exist_ok=True)
    with (workdir / "status").open("a") as fh:
        fh.writelines(line + "\n" for line in lines)


async def _until(predicate: Any, timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.005)


@pytest.mark.asyncio
async def test_rip_cd_reports_each_track_as_abcde_moves_it_while_abcde_still_runs(monkeypatch, tmp_path):
    """abcde records `movetrack-NN` in its status file once track NN's WAV is in the output dir. Each track is
    reported then, while abcde is still ripping the next one, rather than all together when abcde exits."""
    monkeypatch.setattr(abcde_rip, "STATUS_POLL_SECONDS", 0.01)
    exit_now = asyncio.Event()
    fake = _RunningProc(exit_now)

    async def fake_create(*_a: Any, **_kw: Any) -> _RunningProc:
        return fake

    monkeypatch.setattr(abcde_rip.asyncio, "create_subprocess_exec", fake_create)
    reported: list[tuple[int, bool, bool]] = []

    async def on_done(idx: int, result: RipResult) -> None:
        reported.append((idx, result.ok, exit_now.is_set()))

    rip = asyncio.create_task(rip_cd("/dev/sr0", tmp_path, [1, 2], on_track_done=on_done))
    _append_status(tmp_path, "abcde-version=2.9.3", "readtrack-01")
    _write_track_wav(tmp_path, 1)
    _append_status(tmp_path, "movetrack-01", "movetrack-output-wav", "readtrack-02")
    await _until(lambda: len(reported) == 1)
    assert reported == [(1, True, False)]

    _write_track_wav(tmp_path, 2)
    _append_status(tmp_path, "movetrack-02")
    await _until(lambda: len(reported) == 2)
    exit_now.set()
    results = await rip

    assert reported == [(1, True, False), (2, True, False)]
    assert results[2].output_path == tmp_path / "track02.wav"


@pytest.mark.asyncio
async def test_rip_cd_reports_the_wav_bytes_written_so_far_against_the_expected_total(monkeypatch, tmp_path):
    """While abcde runs, the rip reports the bytes of every WAV written so far: tracks already moved into the output
    dir plus the one cdparanoia is still writing in abcde's work dir."""
    monkeypatch.setattr(abcde_rip, "STATUS_POLL_SECONDS", 0.01)
    exit_now = asyncio.Event()
    fake = _RunningProc(exit_now)

    async def fake_create(*_a: Any, **_kw: Any) -> _RunningProc:
        return fake

    monkeypatch.setattr(abcde_rip.asyncio, "create_subprocess_exec", fake_create)
    seen: list[tuple[int, int | None]] = []

    async def on_progress(done: int, total: int | None) -> None:
        seen.append((done, total))

    rip = asyncio.create_task(rip_cd("/dev/sr0", tmp_path, [1, 2], on_progress=on_progress, expected_bytes=5000))
    _write_track_wav(tmp_path, 1, b"a" * 1000)
    _append_status(tmp_path, "movetrack-01")
    (tmp_path / "abcde.fc110d12" / "track02.wav").write_bytes(b"b" * 300)
    await _until(lambda: (1300, 5000) in seen)
    exit_now.set()
    await rip


@pytest.mark.asyncio
async def test_rip_cd_without_a_progress_listener_reports_nothing(monkeypatch, tmp_path):
    _write_track_wav(tmp_path, 1)
    _stub_subprocess(monkeypatch, lines=["Grabbing entire CD - tracks: 01"])
    results = await rip_cd("/dev/sr0", tmp_path, [1], expected_bytes=5000)
    assert results[1].ok


@pytest.mark.asyncio
async def test_rip_cd_logs_abcde_output_for_the_job_log(monkeypatch, tmp_path, caplog):
    """abcde's stdout and stderr go to the service log, which the backend copies into the job's log. A line
    cdparanoia redraws with carriage returns is logged as its last state."""
    _write_track_wav(tmp_path, 1)
    _stub_subprocess(
        monkeypatch,
        lines=["Grabbing entire CD - tracks: 01"],
        stderr_lines=["(== PROGRESS == [  >   ] ==)\r(== PROGRESS == [ done ] ==)"],
    )
    caplog.set_level("DEBUG", logger="arm_ripper.rip.abcde")

    await rip_cd("/dev/sr0", tmp_path, [1])

    logged = [r.getMessage() for r in caplog.records if r.name == "arm_ripper.rip.abcde"]
    assert "abcde: Grabbing entire CD - tracks: 01" in logged
    assert "abcde: (== PROGRESS == [ done ] ==)" in logged


@pytest.mark.asyncio
async def test_rip_cd_fails_a_track_with_the_read_error_abcde_recorded_for_it(monkeypatch, tmp_path):
    """abcde writes `readtrack-NN: <reader> returned code N` to its errors file when a track cannot be read; that
    track fails with it, and the others keep the generic reason."""
    _write_track_wav(tmp_path, 1)
    workdir = tmp_path / "abcde.fc110d12"
    workdir.mkdir()
    (workdir / "errors").write_text("readtrack-02: cdparanoia returned code 1\n")
    _stub_subprocess(monkeypatch, lines=["Grabbing entire CD - tracks: 01 02 03"])

    results = await rip_cd("/dev/sr0", tmp_path, [1, 2, 3])

    assert results[1].ok
    assert results[2].error == "abcde could not read the track: cdparanoia returned code 1"
    assert results[3].error == "abcde did not produce the expected wav file"


@pytest.mark.asyncio
async def test_rip_cd_streams_per_track_callbacks_in_order(monkeypatch, tmp_path):
    """Happy path: abcde moved all three tracks into place; each is reported once, in track order, with size and
    sha256."""
    paths = [_write_track_wav(tmp_path, i) for i in (1, 2, 3)]
    _append_status(tmp_path, "movetrack-01", "movetrack-02", "movetrack-03")
    expected_sizes = [p.stat().st_size for p in paths]
    expected_shas = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]

    _stub_subprocess(
        monkeypatch,
        lines=["Grabbing entire CD - tracks: 01 02 03"],
    )

    callback_log: list[tuple[int, bool, int | None]] = []

    async def on_done(idx: int, result: RipResult) -> None:
        callback_log.append((idx, result.ok, result.size_bytes))

    results = await rip_cd(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        track_indexes=[1, 2, 3],
        on_track_done=on_done,
    )

    assert callback_log == [
        (1, True, expected_sizes[0]),
        (2, True, expected_sizes[1]),
        (3, True, expected_sizes[2]),
    ]
    assert results[1].sha256 == expected_shas[0]
    assert results[2].sha256 == expected_shas[1]
    assert results[3].sha256 == expected_shas[2]
    assert results[1].output_path == tmp_path / "track01.wav"


@pytest.mark.asyncio
async def test_rip_cd_recovers_in_post_wait_sweep_when_wav_lands_after_proc_exits(monkeypatch, tmp_path):
    """A WAV moved into place after the last poll (here, while abcde
    exits) is caught by the post-exit sweep."""
    _write_track_wav(tmp_path, 1)
    # Track 2's WAV will be written by the FakeProc.wait() hook.

    class _FakeProcWithLateMove(_FakeProc):
        def __init__(self, lines: list[bytes]) -> None:
            super().__init__(lines)

        async def wait(self) -> int:
            # Simulate the `move` action completing during the proc-wait
            # window. The post-wait sweep in rip_cd then picks it up.
            _write_track_wav(tmp_path, 2)
            return await super().wait()

    fake = _FakeProcWithLateMove([b"Grabbing entire CD - tracks: 01 02\n"])

    async def fake_create(*_a: Any, **_kw: Any) -> _FakeProcWithLateMove:
        return fake

    monkeypatch.setattr(abcde_rip.asyncio, "create_subprocess_exec", fake_create)

    results = await rip_cd(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        track_indexes=[1, 2],
    )
    assert results[1].ok
    assert results[2].ok


@pytest.mark.asyncio
async def test_rip_cd_subprocess_not_on_path_fails_every_track(monkeypatch, tmp_path):
    async def fake_create(*_a: Any, **_kw: Any) -> _FakeProc:
        raise FileNotFoundError("abcde")

    monkeypatch.setattr(abcde_rip.asyncio, "create_subprocess_exec", fake_create)

    callbacks: list[tuple[int, bool, str | None]] = []

    async def on_done(idx: int, result: RipResult) -> None:
        callbacks.append((idx, result.ok, result.error))

    results = await rip_cd(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        track_indexes=[1, 2, 3],
        on_track_done=on_done,
    )

    assert [c[0] for c in callbacks] == [1, 2, 3]
    assert all(not c[1] for c in callbacks)
    assert all("not on PATH" in (c[2] or "") for c in callbacks)
    assert all(not results[i].ok for i in (1, 2, 3))


@pytest.mark.asyncio
async def test_rip_cd_nonzero_exit_fails_unfinished_tracks_with_stderr_tail(monkeypatch, tmp_path):
    # Track 1 succeeds (its WAV is on disk for the post-exit sweep); track 2 was never
    # finalised → fails with the stderr tail.
    _write_track_wav(tmp_path, 1)
    _stub_subprocess(
        monkeypatch,
        lines=["Grabbing entire CD - tracks: 01 02"],
        stderr_lines=["abcde: catastrophic disc-read failure"],
        returncode=2,
    )

    results = await rip_cd(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        track_indexes=[1, 2],
    )
    assert results[1].ok is True
    assert results[2].ok is False
    assert "catastrophic" in (results[2].error or "")


@pytest.mark.asyncio
async def test_rip_cd_timeout_fails_unfinished_tracks(monkeypatch, tmp_path):
    """Whole-rip timeout kicks in; every unfinalised track gets a
    timeout failure. Track 1 had already succeeded before the timeout
    so it keeps its success result."""
    _write_track_wav(tmp_path, 1)
    _append_status(tmp_path, "movetrack-01")
    monkeypatch.setattr(abcde_rip, "STATUS_POLL_SECONDS", 0.01)

    # FakeProc.wait() hangs forever (until kill() lands a returncode);
    # asyncio.wait_for around the stream-and-wait wrapper trips the
    # timeout. After timeout the finally block in rip_cd calls
    # proc.kill() + proc.wait(); the wait must then return immediately,
    # mirroring real subprocess.Process semantics.
    class _HangingProc(_FakeProc):
        async def wait(self) -> int:
            if self.returncode is not None:
                return self.returncode
            await asyncio.sleep(3600)
            return 0

    fake = _HangingProc([b"Grabbing entire CD - tracks: 01 02\n"])

    async def fake_create(*_a: Any, **_kw: Any) -> _HangingProc:
        return fake

    monkeypatch.setattr(abcde_rip.asyncio, "create_subprocess_exec", fake_create)
    monkeypatch.setattr(abcde_rip, "CD_RIP_TIMEOUT_SECONDS", 0.05)

    callbacks: list[tuple[int, bool, str | None]] = []

    async def on_done(idx: int, result: RipResult) -> None:
        callbacks.append((idx, result.ok, result.error))

    results = await rip_cd(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        track_indexes=[1, 2],
        on_track_done=on_done,
    )
    assert results[1].ok is True
    assert results[2].ok is False
    assert "timed out" in (results[2].error or "")
    # Track 1's callback fired from a poll during the rip; track 2's was
    # fired by the post-timeout failure sweep.
    assert sorted(c[0] for c in callbacks) == [1, 2]


@pytest.mark.asyncio
async def test_rip_cd_without_callback_still_returns_dict(monkeypatch, tmp_path):
    _write_track_wav(tmp_path, 1)
    _stub_subprocess(monkeypatch, lines=["Grabbing entire CD - tracks: 01 02"])

    results = await rip_cd(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        track_indexes=[1],
        on_track_done=None,
    )
    assert results[1].ok is True


@pytest.mark.asyncio
async def test_rip_cd_runs_abcde_with_cwd_set_to_output_dir(monkeypatch, tmp_path):
    """Regression: abcde stages WAVs in a per-rip `abcde.XXXXX/` temp
    dir relative to its CWD. The ripper container's default CWD is
    read-only for non-root users — without `cwd=` the very first track
    fails with "Permission denied" on the temp-dir mkdir. Pin the cwd
    arg to `output_dir` so the temp tree lands inside the writable raw
    output tree."""
    captured: dict[str, Any] = {}

    async def fake_create(*_a: Any, **kw: Any) -> _FakeProc:
        captured.update(kw)
        return _FakeProc([])

    monkeypatch.setattr(abcde_rip.asyncio, "create_subprocess_exec", fake_create)
    await rip_cd(device_path="/dev/sr0", output_dir=tmp_path, track_indexes=[1])
    assert captured.get("cwd") == str(tmp_path)


def test_abcde_config_disables_the_lookup_with_abcdes_own_spelling(tmp_path):
    """The `move` action turns abcde's lookup phase on (DOCDDB=y), and that phase only honours a lowercase
    `CDDBAVAIL=n` and only skips the query for the `cddb` method; `musicbrainz` queries regardless. The
    method must still be one abcde accepts at startup."""
    lines = abcde_rip._abcde_config(tmp_path).splitlines()
    assert 'CDDBAVAIL="n"' in lines
    assert 'CDDBMETHOD="cddb"' in lines
    assert 'CDDBAVAIL="N"' not in lines
    assert not any("musicbrainz" in line for line in lines)


def test_abcde_config_lands_wavs_at_output_dir_via_force_y(tmp_path):
    """Regression: abcde's `do_move()` WAV branch is gated on
    `DOCLEAN=y || FORCE=y` — without one of those set, `ACTIONS` of
    `read,move` silently skips the move and WAVs stay in the
    `abcde.${CDDBDISCID}/` staging directory rather than landing at
    `OUTPUTDIR/trackNN.wav` where ARM looks for them. Pin `FORCE=y` so
    move actually runs; pin `OUTPUTFORMAT='track${TRACKNUM}'` so the
    post-move name matches the pre-move name (avoids needing two
    distinct filename probes in `_finalize_track`)."""
    conf = abcde_rip._abcde_config(tmp_path)
    assert f'OUTPUTDIR="{tmp_path}"' in conf
    assert 'FORCE="y"' in conf
    # OUTPUTFORMAT must not reference ARTISTFILE/ALBUMFILE/TRACKFILE —
    # they're empty under CDDBAVAIL=N and produce broken paths.
    for line in conf.splitlines():
        if line.startswith("OUTPUTFORMAT="):
            fmt = line.split("=", 1)[1]
            for forbidden in ("ARTISTFILE", "ALBUMFILE", "TRACKFILE"):
                assert forbidden not in fmt
    for line in conf.splitlines():
        if line.startswith("ACTIONS="):
            actions = line.split("=", 1)[1].strip().strip('"').split(",")
            assert "read" in actions
            assert "move" in actions


@pytest.mark.asyncio
async def test_rip_cd_clean_exit_but_wav_missing_yields_failure(monkeypatch, tmp_path):
    """abcde exits 0 but the track WAV never landed (silent per-track
    failure on a partially scratched disc). The track comes back failed
    with a clear reason rather than appearing in `results` as missing."""
    _stub_subprocess(monkeypatch, lines=[])

    results = await rip_cd(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        track_indexes=[1],
    )
    assert results[1].ok is False
    assert "did not produce" in (results[1].error or "")


@pytest.mark.asyncio
async def test_rip_cd_kills_the_whole_process_group_on_timeout(monkeypatch, tmp_path, killpg_calls):
    """abcde forks cdparanoia per track. Killing bash alone left
    cdparanoia holding the drive; the spawn must start a new session and
    the kill must target its process group."""

    class _HangingProc(_FakeProc):
        async def wait(self) -> int:
            if self.returncode is not None:
                return self.returncode
            await asyncio.sleep(3600)
            return 0

    captured: dict[str, Any] = {}
    fake = _HangingProc([])

    async def fake_create(*_a: Any, **kw: Any) -> _HangingProc:
        captured.update(kw)
        return fake

    monkeypatch.setattr(abcde_rip.asyncio, "create_subprocess_exec", fake_create)
    monkeypatch.setattr(abcde_rip, "CD_RIP_TIMEOUT_SECONDS", 0.05)

    results = await rip_cd(device_path="/dev/sr0", output_dir=tmp_path, track_indexes=[1])
    assert captured.get("start_new_session") is True
    assert killpg_calls == [(_FAKE_PID, abcde_rip.signal.SIGKILL)]
    assert results[1].ok is False


def test_kill_group_tolerates_an_already_empty_group(monkeypatch):
    def gone(_pgid: int, _sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(abcde_rip.os, "killpg", gone)
    fake = _FakeProc([])
    abcde_rip._kill_group(fake)  # type: ignore[arg-type]
    assert fake.returncode == -9


def test_write_config_writes_the_abcde_config_to_a_temp_file(tmp_path):
    conf_path = abcde_rip._write_config(tmp_path)
    try:
        assert conf_path.exists()
        assert conf_path.name.endswith(".abcde.conf")
        assert conf_path.read_text() == abcde_rip._abcde_config(tmp_path)
    finally:
        conf_path.unlink()


@pytest.mark.asyncio
async def test_spawn_abcde_runs_abcde_in_its_own_session_from_the_output_dir(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}
    fake = _FakeProc([])

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProc:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return fake

    monkeypatch.setattr(abcde_rip.asyncio, "create_subprocess_exec", fake_create)
    conf_path = tmp_path / "x.abcde.conf"

    proc = await abcde_rip._spawn_abcde("/dev/sr0", conf_path, tmp_path)

    assert captured["args"] == ("abcde", "-d", "/dev/sr0", "-c", str(conf_path), "-N", "-n", "-j", "1")
    assert captured["kwargs"] == {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "cwd": str(tmp_path),
        "start_new_session": True,
    }
    assert proc is fake


def _recording_tracks(tmp_path: Path, indexes: list[int], *, with_callback: bool = True):
    calls: list[tuple[int, RipResult]] = []

    async def on_done(idx: int, result: RipResult) -> None:
        calls.append((idx, result))

    tracks = abcde_rip._CdTracks(tmp_path, indexes, on_done if with_callback else None)
    return tracks, calls


async def test_cd_tracks_finalize_records_the_wav_and_fires_the_callback_once(tmp_path):
    (tmp_path / "track01.wav").write_bytes(b"abc")
    tracks, calls = _recording_tracks(tmp_path, [1])

    await tracks.finalize(1)
    first = tracks.results[1]
    await tracks.finalize(1)

    assert first.ok is True
    assert first.size_bytes == 3
    assert first.duration_seconds == 0
    assert first.sha256 == hashlib.sha256(b"abc").hexdigest()
    assert tracks.results[1] is first
    assert calls == [(1, first)]


async def test_cd_tracks_finalize_without_a_wav_leaves_no_result(tmp_path):
    tracks, calls = _recording_tracks(tmp_path, [1])

    await tracks.finalize(1)

    assert tracks.results == {}
    assert calls == []


async def test_cd_tracks_finalize_without_a_callback_still_records_the_result(tmp_path):
    (tmp_path / "track01.wav").write_bytes(b"abc")
    tracks, _ = _recording_tracks(tmp_path, [1], with_callback=False)

    await tracks.finalize(1)

    assert tracks.results[1].ok is True


async def test_cd_tracks_finalize_moved_finalizes_requested_moved_tracks_in_track_order(tmp_path):
    for idx in (1, 2, 3):
        (tmp_path / f"track{idx:02d}.wav").write_bytes(b"abc")
    tracks, calls = _recording_tracks(tmp_path, [1, 2])

    await tracks.finalize_moved({3, 2, 1})

    assert [idx for idx, _ in calls] == [1, 2]


async def test_cd_tracks_finalize_moved_picks_up_a_moved_track_once_its_wav_is_visible(tmp_path):
    tracks, calls = _recording_tracks(tmp_path, [1])

    await tracks.finalize_moved({1})
    assert tracks.results == {}

    (tmp_path / "track01.wav").write_bytes(b"abc")
    await tracks.finalize_moved({1})
    await tracks.finalize_moved({1})

    assert [idx for idx, _ in calls] == [1]


async def test_finalize_moved_tracks_finalizes_what_the_status_file_lists_as_moved(tmp_path):
    (tmp_path / "track01.wav").write_bytes(b"abc")
    (tmp_path / "track02.wav").write_bytes(b"abc")
    _append_status(tmp_path, "readtrack-01", "movetrack-01", "movetrack-output-wav", "readtrack-02")
    tracks, calls = _recording_tracks(tmp_path, [1, 2])

    await abcde_rip._finalize_moved_tracks(tmp_path, tracks)

    assert [idx for idx, _ in calls] == [1]


async def test_cd_tracks_fail_remaining_skips_finalized_tracks(tmp_path):
    (tmp_path / "track01.wav").write_bytes(b"abc")
    tracks, calls = _recording_tracks(tmp_path, [1, 2])
    await tracks.finalize(1)

    await tracks.fail_remaining("boom")

    assert tracks.results[1].ok is True
    assert tracks.results[2].ok is False
    assert tracks.results[2].error == "boom"
    assert [idx for idx, _ in calls] == [1, 2]


async def test_cd_tracks_fail_remaining_without_a_callback_records_failures(tmp_path):
    tracks, _ = _recording_tracks(tmp_path, [1], with_callback=False)

    await tracks.fail_remaining("boom")

    assert tracks.results[1].ok is False


async def test_cd_tracks_finalize_pending_finalizes_only_tracks_without_a_result(tmp_path):
    (tmp_path / "track01.wav").write_bytes(b"abc")
    (tmp_path / "track02.wav").write_bytes(b"abcd")
    tracks, calls = _recording_tracks(tmp_path, [1, 2, 3])
    await tracks.finalize(1)

    await tracks.finalize_pending()

    assert sorted(tracks.results) == [1, 2]
    assert [idx for idx, _ in calls] == [1, 2]


async def test_read_until_exit_reads_stdout_to_the_end_then_returns_the_exit_code():
    proc = _FakeProc([b"first\n", b"second\n", b"third\n"], returncode=3)

    rc = await abcde_rip._read_until_exit(proc)  # type: ignore[arg-type]

    assert rc == 3
    assert proc.stdout._lines == []


def _stop_abcde_setup(monkeypatch, tmp_path, *, returncode: int | None):
    killpg_calls: list[tuple[int, int]] = []
    monkeypatch.setattr(abcde_rip.os, "killpg", lambda pgid, sig: killpg_calls.append((pgid, sig)))
    proc = _FakeProc([])
    proc.returncode = returncode
    conf_path = tmp_path / "x.abcde.conf"
    conf_path.write_text("conf")
    return proc, conf_path, killpg_calls


async def _finished_task() -> asyncio.Task[None]:
    async def done() -> None:
        return None

    task = asyncio.ensure_future(done())
    await task
    return task


async def test_stop_abcde_kills_and_reaps_a_running_process_and_deletes_the_config(monkeypatch, tmp_path):
    proc, conf_path, killpg_calls = _stop_abcde_setup(monkeypatch, tmp_path, returncode=None)

    await abcde_rip._stop_abcde(proc, await _finished_task(), conf_path)  # type: ignore[arg-type]

    assert killpg_calls == [(_FAKE_PID, abcde_rip.signal.SIGKILL)]
    assert proc.returncode == -9
    assert not conf_path.exists()


async def test_stop_abcde_leaves_an_exited_process_alone_and_deletes_the_config(monkeypatch, tmp_path):
    proc, conf_path, killpg_calls = _stop_abcde_setup(monkeypatch, tmp_path, returncode=0)

    await abcde_rip._stop_abcde(proc, await _finished_task(), conf_path)  # type: ignore[arg-type]

    assert killpg_calls == []
    assert not conf_path.exists()


async def test_stop_abcde_swallows_a_failing_reap(monkeypatch, tmp_path):
    proc, conf_path, killpg_calls = _stop_abcde_setup(monkeypatch, tmp_path, returncode=None)

    async def failing_wait() -> int:
        raise RuntimeError("reap failed")

    monkeypatch.setattr(proc, "wait", failing_wait)

    await abcde_rip._stop_abcde(proc, await _finished_task(), conf_path)  # type: ignore[arg-type]

    assert len(killpg_calls) == 1
    assert not conf_path.exists()


async def test_stop_abcde_swallows_a_cancelled_stderr_task_and_tolerates_a_missing_config(monkeypatch, tmp_path):
    proc, conf_path, _ = _stop_abcde_setup(monkeypatch, tmp_path, returncode=0)
    conf_path.unlink()

    async def forever() -> None:
        await asyncio.sleep(3600)

    task = asyncio.ensure_future(forever())
    await asyncio.sleep(0)
    task.cancel()

    await abcde_rip._stop_abcde(proc, task, conf_path)  # type: ignore[arg-type]

    assert task.cancelled()
    assert not conf_path.exists()


def test_exit_failure_reports_the_last_400_characters_of_stderr_on_a_non_zero_exit():
    stderr_lines = ["early noise " * 50, "  the real error  "]

    message = abcde_rip._exit_failure(2, stderr_lines)

    expected_tail = "\n".join(stderr_lines).strip()[-400:]
    assert message == f"abcde failed: {expected_tail}"
    assert len(expected_tail) == 400
    assert message.endswith("the real error")


@pytest.mark.parametrize("stderr_lines", [[], ["", "   "]])
def test_exit_failure_falls_back_to_the_exit_code_when_stderr_is_blank(stderr_lines):
    assert abcde_rip._exit_failure(3, stderr_lines) == "abcde failed: exit=3"


def test_exit_failure_reports_a_missing_wav_on_a_zero_exit():
    assert abcde_rip._exit_failure(0, ["ignored"]) == "abcde did not produce the expected wav file"


def test_output_line_keeps_the_last_state_of_a_redrawn_line():
    assert abcde_rip._output_line(b"(== 10% ==)\r(== 55% ==)\r(== 100% ==)\n") == "(== 100% ==)"


def test_output_line_of_a_plain_line_is_the_line():
    assert abcde_rip._output_line(b"Grabbing track 01: Overture...\n") == "Grabbing track 01: Overture..."


def test_log_output_skips_a_blank_line(caplog):
    caplog.set_level("DEBUG", logger="arm_ripper.rip.abcde")
    abcde_rip._log_output("")
    assert caplog.records == []


def test_log_output_logs_an_ordinary_line_at_debug(caplog):
    caplog.set_level("DEBUG", logger="arm_ripper.rip.abcde")
    abcde_rip._log_output("Grabbing track 01: Overture...")
    assert [(r.levelname, r.getMessage()) for r in caplog.records] == [
        ("DEBUG", "abcde: Grabbing track 01: Overture...")
    ]


@pytest.mark.parametrize("line", ["[ERROR] abcde: CDROM has not been defined", "[WARNING] abcde: no CD found"])
def test_log_output_logs_abcdes_own_error_and_warning_lines_at_warning(caplog, line):
    caplog.set_level("DEBUG", logger="arm_ripper.rip.abcde")
    abcde_rip._log_output(line)
    assert [(r.levelname, r.getMessage()) for r in caplog.records] == [("WARNING", f"abcde: {line}")]


async def test_cd_tracks_finalize_measures_the_track_length_from_the_wav(tmp_path):
    """The ripped length comes from the WAV itself, so the job log and the track row carry it like a MakeMKV title."""
    (tmp_path / "track01.wav").write_bytes(b"\0" * (3 * 176_400 + 44))
    tracks, _ = _recording_tracks(tmp_path, [1])

    await tracks.finalize(1)

    assert tracks.results[1].duration_seconds == 3


@pytest.mark.asyncio
async def test_rip_cd_logs_its_start_at_debug_only(monkeypatch, tmp_path, caplog):
    """rip.started already announces the rip at info; the device and work dir line is detail."""
    _write_track_wav(tmp_path, 1)
    _stub_subprocess(monkeypatch, lines=[])
    caplog.set_level("DEBUG", logger="arm_ripper.rip.abcde")

    await rip_cd("/dev/sr0", tmp_path, [1])

    start = [r for r in caplog.records if r.getMessage().startswith("abcde rip device=")]
    assert [r.levelname for r in start] == ["DEBUG"]
