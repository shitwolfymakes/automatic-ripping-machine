"""End-to-end exercise of `rip_cd` against a faked abcde subprocess.

The fake replaces `asyncio.create_subprocess_exec` with a stub process
whose stdout streams a canned trace of abcde output. As the trace says
each track finished reading, the test arranges for the matching
`track_NN.wav` file to appear in the output directory; `rip_cd` then
fires its `on_track_done` callback. Covers:

  - Streaming happy path: each callback fires once, in stream order,
    with a populated RipResult (size + sha256).
  - Race tolerance: a track-done log line arrives before the WAV file
    is on disk; the post-wait sweep catches it.
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


def _done_line(track: int) -> str:
    return f"[wavencode] Track {track:02d}: Reading audio from sectors 1000-2000...done"


@pytest.mark.asyncio
async def test_rip_cd_streams_per_track_callbacks_in_order(monkeypatch, tmp_path):
    """Happy path. Each of 3 tracks: the done-line arrives, the WAV
    appears immediately, the callback fires. By end of stream all three
    are reported with size + sha256."""
    # Pre-write the WAVs so they're already on disk when the done-line
    # is parsed (simulates a fast `move` action).
    paths = [_write_track_wav(tmp_path, i) for i in (1, 2, 3)]
    expected_sizes = [p.stat().st_size for p in paths]
    expected_shas = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]

    _stub_subprocess(
        monkeypatch,
        lines=[
            "Grabbing entire CD - tracks: 01 02 03",
            _done_line(1),
            "[mv] Track 01: Moving ...done",
            _done_line(2),
            "[mv] Track 02: Moving ...done",
            _done_line(3),
            "[mv] Track 03: Moving ...done",
        ],
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
async def test_rip_cd_recovers_when_wav_appears_after_done_line(monkeypatch, tmp_path):
    """The `move` action sometimes finishes after the `Reading...done`
    line is emitted. The per-line stdout sweep catches the WAV when it
    appears on a subsequent tick."""
    appeared: dict[int, bool] = {1: False, 2: False}

    def _maybe_drop_track2() -> None:
        # On the third stdout read, drop track 2's WAV to disk.
        # That gives the rip_cd loop time to see the done-line at
        # read #2 (where the WAV does NOT yet exist), then sweep
        # again at read #3 (where it DOES).
        if not appeared[2]:
            return
        _write_track_wav(tmp_path, 2)

    # Track 1's WAV is already on disk; track 2's only appears after
    # we've started reading stdout.
    _write_track_wav(tmp_path, 1)

    read_count = [0]

    def on_each_read() -> None:
        read_count[0] += 1
        # After the third readline (which returns the track-2 done line),
        # drop the WAV so the NEXT sweep finds it.
        if read_count[0] == 4:
            _write_track_wav(tmp_path, 2)
            appeared[2] = True

    _stub_subprocess(
        monkeypatch,
        lines=[
            "Grabbing entire CD - tracks: 01 02",
            _done_line(1),
            _done_line(2),
            "[mv] Track 02: Moving ...done",
        ],
        on_each_stdout_read=on_each_read,
    )

    callbacks: list[int] = []

    async def on_done(idx: int, _result: RipResult) -> None:
        callbacks.append(idx)

    results = await rip_cd(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        track_indexes=[1, 2],
        on_track_done=on_done,
    )

    # Both tracks finalized; track 2 came in via the post-line sweep.
    assert sorted(callbacks) == [1, 2]
    assert results[1].ok
    assert results[2].ok
    # Don't deliberately drop in a clean test (silence unused-var warning).
    _ = _maybe_drop_track2


@pytest.mark.asyncio
async def test_rip_cd_recovers_in_post_wait_sweep_when_wav_lands_after_proc_exits(monkeypatch, tmp_path):
    """If a WAV file is moved into place AFTER the last stdout line has
    been read (i.e. between the streamer exiting and proc.wait()
    returning), the post-wait sweep catches it."""
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

    encoded = [(line + "\n").encode() for line in [_done_line(1), _done_line(2)]]
    fake = _FakeProcWithLateMove(encoded)

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
    # Track 1 succeeds (WAV on disk + done-line); track 2 was never
    # finalised → fails with the stderr tail.
    _write_track_wav(tmp_path, 1)
    _stub_subprocess(
        monkeypatch,
        lines=[_done_line(1)],
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

    encoded = [(line + "\n").encode() for line in [_done_line(1)]]
    fake = _HangingProc(encoded)

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
    # Track 1's callback fired during the stream; track 2's was fired by
    # the post-timeout failure sweep.
    assert sorted(c[0] for c in callbacks) == [1, 2]


@pytest.mark.asyncio
async def test_rip_cd_without_callback_still_returns_dict(monkeypatch, tmp_path):
    _write_track_wav(tmp_path, 1)
    _stub_subprocess(monkeypatch, lines=[_done_line(1)])

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


def test_abcde_config_uses_valid_cddbmethod_and_disables_lookup(tmp_path):
    """Regression: abcde validates `CDDBMETHOD` at startup against an
    allowlist (cdtext, cddb, musicbrainz). Passing `none` makes it abort
    with "Unknown lookup method none". To actually skip metadata lookup,
    set `CDDBAVAIL=N`; keep `CDDBMETHOD` set to a real method so the
    keyword parses."""
    conf = abcde_rip._abcde_config(tmp_path)
    assert 'CDDBAVAIL="N"' in conf
    assert 'CDDBMETHOD="none"' not in conf
    # The CDDBMETHOD value, if present, must be one abcde recognises.
    for line in conf.splitlines():
        if line.startswith("CDDBMETHOD="):
            value = line.split("=", 1)[1].strip().strip('"')
            assert value in {"cdtext", "cddb", "musicbrainz"}


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


async def test_cd_tracks_note_line_ignores_lines_that_are_not_track_done(tmp_path):
    (tmp_path / "track01.wav").write_bytes(b"abc")
    tracks, calls = _recording_tracks(tmp_path, [1])

    await tracks.note_line("Grabbing entire CD...")

    assert tracks.results == {}
    assert calls == []


async def test_cd_tracks_note_line_finalizes_a_logged_track_once_its_wav_lands(tmp_path):
    tracks, calls = _recording_tracks(tmp_path, [1])

    await tracks.note_line(_done_line(1))
    assert tracks.results == {}

    (tmp_path / "track01.wav").write_bytes(b"abc")
    await tracks.note_line("some later line")

    assert list(tracks.results) == [1]
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


async def test_read_until_exit_feeds_every_stdout_line_to_tracks_then_returns_the_exit_code(tmp_path):
    seen: list[str] = []

    class _RecordingTracks(abcde_rip._CdTracks):
        async def note_line(self, line: str) -> None:
            seen.append(line)

    tracks = _RecordingTracks(tmp_path, [1], None)
    proc = _FakeProc([b"first\n", b"second\n", b"third\n"], returncode=3)

    rc = await abcde_rip._read_until_exit(proc, tracks)  # type: ignore[arg-type]

    assert seen == ["first", "second", "third"]
    assert rc == 3


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
