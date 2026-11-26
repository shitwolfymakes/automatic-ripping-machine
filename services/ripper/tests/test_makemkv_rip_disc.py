"""End-to-end exercise of `rip_disc` against a faked makemkvcon.

The fake replaces `asyncio.create_subprocess_exec` with a stub process
whose stdout streams a canned robot-mode trace; `rip_disc` walks the
trace, fires the lifecycle hooks, and walks the (faked) output dir to
attribute per-title outcomes. Confirms:

  - PRGT "Saving title #N" transitions current_title and emits
    on_title_start once per title.
  - PRGV ramps fire on_title_progress against the right title.
  - MSG:5003 captures per-title failure reason; the matching file is
    absent from the output dir, so the title comes back FAILED with
    that reason rather than "produced no .mkv".
  - Successful titles produce title_tNN.mkv, get sha256+size
    populated, and come back ok=True.
  - Tracks not announced in the stream but present on disk are still
    attributed (PRGT-miss safety net).
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

import pytest

import arm_ripper.rip.makemkv_process as makemkv_process
import arm_ripper.rip.makemkv_rip as makemkv_rip
import arm_ripper.rip.makemkv_stream as makemkv_stream
import arm_ripper.rip.subprocess_cleanup as subprocess_cleanup
from arm_ripper.rip.makemkv_rip import rip_disc
from arm_ripper.rip.result import RipResult


class _FakeStream:
    """Async-readable stream emitting canned lines."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)

    async def read(self) -> bytes:
        return b""


class _FakeProc:
    def __init__(self, stdout_lines: list[bytes], returncode: int = 0) -> None:
        self.stdout = _FakeStream(stdout_lines)
        self.stderr = _FakeStream([])
        self.returncode: int | None = None
        self._final_returncode = returncode

    async def wait(self) -> int:
        # Yield control so the streamer task gets to drain stdout
        # before this resolves; mirrors real subprocess timing.
        await asyncio.sleep(0)
        self.returncode = self._final_returncode
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


def _stub_subprocess(monkeypatch, lines: list[str], returncode: int = 0) -> _FakeProc:
    """Replace asyncio.create_subprocess_exec with a factory returning a
    _FakeProc preloaded with `lines`. Returns the proc so a test can
    inspect post-rip state if needed."""
    encoded = [(line + "\n").encode() for line in lines]
    fake = _FakeProc(encoded, returncode=returncode)

    async def fake_create_subprocess_exec(*_args: Any, **_kwargs: Any) -> _FakeProc:
        return fake

    monkeypatch.setattr(makemkv_rip.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    return fake


def _write_title_file(output_dir: Path, idx: int, content: bytes = b"x" * 64) -> Path:
    p = output_dir / f"title_t{idx:02d}.mkv"
    p.write_bytes(content)
    return p


@pytest.mark.asyncio
async def test_rip_disc_attributes_files_to_eligible_source_indexes(monkeypatch, tmp_path):
    """In `mkv all` mode MakeMKV writes `<volume_label>_tNN.mkv` files
    where NN is the *output position*, not the source title index.
    rip_disc pairs the output files (sorted by `_tNN`) positionally
    with the eligible-source-index list the dispatcher provides — so
    a disc where source titles 0 and 2 are eligible (1 below minlength)
    sees `_t00.mkv` ↦ source 0, `_t01.mkv` ↦ source 2."""
    _stub_subprocess(
        monkeypatch,
        [
            'MSG:1005,0,1,"MakeMKV started","%1 started","..."',
            'PRGT:5024,0,"Saving all titles to MKV files"',
            "PRGV:5000,5000,10000",
            'MSG:5036,0,2,"Copy complete. 2 titles saved.","Copy complete. %1 %2","2","titles"',
        ],
    )
    content_main = b"alpha-bytes" * 8
    content_extra = b"beta-bytes" * 8
    # MakeMKV uses the disc's volume label as the filename prefix —
    # the test fixture mimics that to confirm the glob is label-agnostic.
    (tmp_path / "Movie Title_t00.mkv").write_bytes(content_main)
    (tmp_path / "Movie Title_t01.mkv").write_bytes(content_extra)

    result = await rip_disc(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        minlength_seconds=600,
        eligible_source_indexes=[0, 2],
    )

    assert result.overall_error is None
    assert set(result.titles.keys()) == {0, 2}
    assert result.titles[0].ok is True
    assert result.titles[0].size_bytes == len(content_main)
    assert result.titles[0].sha256 == hashlib.sha256(content_main).hexdigest()
    assert result.titles[0].output_path == tmp_path / "Movie Title_t00.mkv"
    # Source title 2 mapped positionally to the second output file.
    assert result.titles[2].ok is True
    assert result.titles[2].output_path == tmp_path / "Movie Title_t01.mkv"


@pytest.mark.asyncio
async def test_rip_disc_eligible_without_file_marked_failed(monkeypatch, tmp_path):
    """If MakeMKV produced fewer files than the eligible list expected
    (e.g. a title failed mid-rip and got rolled back), the missing
    eligible source indexes come back FAILED with a clear reason."""
    _stub_subprocess(
        monkeypatch,
        [
            'PRGT:5024,0,"Saving all titles to MKV files"',
            'MSG:5036,0,2,"Copy complete. 1 titles saved.","Copy complete. %1 %2","1","titles"',
        ],
    )
    (tmp_path / "Disc_t00.mkv").write_bytes(b"only one made it")

    result = await rip_disc(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        minlength_seconds=120,
        eligible_source_indexes=[0, 2, 5],
    )

    assert result.overall_error is None
    assert result.titles[0].ok is True
    assert result.titles[2].ok is False
    assert "no .mkv" in (result.titles[2].error or "")
    assert result.titles[5].ok is False


@pytest.mark.asyncio
async def test_rip_disc_failed_title_carries_msg5003_reason(monkeypatch, tmp_path):
    """If MSG:5003 captures a per-title failure reason — rare in `mkv
    all` mode but possible — the corresponding source index in the
    result dict carries that reason. The dispatcher surfaces it
    upstream as the track's `last_error`."""
    _stub_subprocess(
        monkeypatch,
        [
            'PRGT:5024,0,"Saving all titles to MKV files"',
            'MSG:5003,0,2,"Failed to save title 1 to file title_t01.mkv",'
            '"Failed to save title %1 to file %2","1","title_t01.mkv"',
        ],
    )
    (tmp_path / "Disc_t00.mkv").write_bytes(b"title 0 succeeded")

    result = await rip_disc(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        minlength_seconds=600,
        eligible_source_indexes=[0],
    )

    assert result.overall_error is None
    assert result.titles[0].ok is True
    # Source title 1 wasn't in the eligible list, so attribution
    # surfaces it via the MSG:5003 reason captured during the rip.
    assert result.titles[1].ok is False
    assert "Failed to save title 1" in (result.titles[1].error or "")


@pytest.mark.asyncio
async def test_rip_disc_overall_failure_surfaces_diagnostics(monkeypatch, tmp_path):
    """Non-zero exit → overall_error set; per-title state discarded so
    the dispatcher fails every selected track with the disc-level reason."""
    _stub_subprocess(
        monkeypatch,
        [
            'MSG:3032,260,4,"Region setting of drive does not match disc",'
            '"Region setting of drive does not match disc"',
            'MSG:1002,32,1,"LIBMKV_TRACE: Exception: Error while reading input",'
            '"LIBMKV_TRACE: %1","Exception: Error while reading input"',
        ],
        returncode=1,
    )

    result = await rip_disc(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        minlength_seconds=600,
    )

    assert result.overall_error is not None
    assert "Region setting" in result.overall_error
    assert "Error while reading input" in result.overall_error
    assert result.titles == {}


@pytest.mark.asyncio
async def test_rip_disc_extra_output_files_left_unclaimed(monkeypatch, tmp_path):
    """If MakeMKV writes more files than the eligible list expected
    (rare — MakeMKV picked up a title our scan missed), the extras
    stay on disk for the user but aren't claimed by any source index.
    The eligible list is the source of truth for attribution."""
    _stub_subprocess(
        monkeypatch,
        [
            'MSG:5036,0,2,"Copy complete. 2 titles saved.","Copy complete. %1 %2","2","titles"',
        ],
    )
    (tmp_path / "Disc_t00.mkv").write_bytes(b"first")
    (tmp_path / "Disc_t01.mkv").write_bytes(b"second")

    result = await rip_disc(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        minlength_seconds=120,
        eligible_source_indexes=[0],  # only one eligible title
    )

    assert result.overall_error is None
    assert 0 in result.titles
    assert result.titles[0].ok is True
    # The second file isn't claimed because no eligible source index maps to it.
    assert len(result.titles) == 1


@pytest.mark.asyncio
async def test_rip_disc_falls_back_to_disc_progress_when_no_per_title_prgt(monkeypatch, tmp_path):
    """`mkv all` emits only the overall "Saving all titles to MKV files"
    PRGT — no per-title milestones. PRGV lines that arrive while
    `current_title is None` must drive `on_disc_progress` via the
    `total/max` channel, not get silently dropped.

    This is the regression that made the dashboard bar stay at 0 % for
    the entire rip even though the file was being written: the streamer
    gated `on_title_progress` on `current_title is not None` and had no
    fallback for the disc-overall case."""
    _stub_subprocess(
        monkeypatch,
        [
            'PRGT:5024,0,"Saving all titles to MKV files"',
            # current/max = 0.10, total/max = 0.05  →  expect disc-level 0.05
            "PRGV:1000,500,10000",
            "PRGV:5000,2500,10000",
            "PRGV:9000,9500,10000",
        ],
    )
    (tmp_path / "Disc_t00.mkv").write_bytes(b"x" * 64)

    title_progress: list[tuple[int, float]] = []
    disc_progress: list[float] = []

    async def on_title_start(_idx: int) -> None:
        return None

    async def on_title_progress(idx: int, frac: float) -> None:
        title_progress.append((idx, frac))

    async def on_disc_progress(frac: float) -> None:
        disc_progress.append(frac)

    result = await rip_disc(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        minlength_seconds=120,
        eligible_source_indexes=[0],
        on_title_start=on_title_start,
        on_title_progress=on_title_progress,
        on_disc_progress=on_disc_progress,
    )

    assert result.overall_error is None
    # No "Saving title N" PRGT → on_title_progress must never have fired.
    assert title_progress == []
    # Disc-level callback got the `total/max` channel (not `current/max`).
    assert disc_progress == [0.05, 0.25, 0.95]


@pytest.mark.asyncio
async def test_rip_disc_pre_save_phase_prgv_is_silently_dropped(monkeypatch, tmp_path):
    """Pre-rip PRGV lines (analyse / decrypt / BD+ phases) have a
    `total/max` channel that climbs to 70-80% within those phases,
    then resets to 0 when MakeMKV enters the save phase.

    If the streamer fired `on_disc_progress` for those, the rips
    store would publish a 70-80% bar to the dashboard, then snap to
    0% when PRGC:5017,0 fires per-title progress — and the ETA
    baseline (anchored at the first sample) would treat the snap as
    a sustained negative pctDelta, holding ETA null until per-title
    progress climbs back past the pre-rip peak (basically forever
    on a long main feature). Gate fixes the regression: PRGV before
    PRGT:5024 is silent."""
    _stub_subprocess(
        monkeypatch,
        [
            # Pre-rip phase — analyse total climbs to ~78%, then resets.
            "PRGV:51819,46899,65536",
            "PRGV:65536,51200,65536",
            "PRGV:0,0,65536",
            # Save phase begins.
            'PRGT:5024,0,"Saving all titles to MKV files"',
            'PRGC:5017,0,"Saving to MKV file"',
            "PRGV:5000,1000,10000",  # per-op 0.5, attributed to title
        ],
    )
    (tmp_path / "Disc_t00.mkv").write_bytes(b"x" * 64)

    title_progress: list[tuple[int, float]] = []
    disc_progress: list[float] = []

    async def on_title_start(_idx: int) -> None:
        return None

    async def on_title_progress(idx: int, frac: float) -> None:
        title_progress.append((idx, frac))

    async def on_disc_progress(frac: float) -> None:
        disc_progress.append(frac)

    result = await rip_disc(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        minlength_seconds=120,
        eligible_source_indexes=[0],
        on_title_start=on_title_start,
        on_title_progress=on_title_progress,
        on_disc_progress=on_disc_progress,
    )

    assert result.overall_error is None
    # Pre-rip PRGV → silent. Per-title PRGV after PRGC:5017,0 fires for source 0.
    assert title_progress == [(0, 0.5)]
    # Disc-level fallback never fired — pre-rip gated, save phase had PRGC:5017.
    assert disc_progress == []


@pytest.mark.asyncio
async def test_rip_disc_per_title_progress_takes_precedence_over_disc(monkeypatch, tmp_path):
    """When a per-title "Saving title #N" PRGT has identified the
    in-flight title, PRGV drives `on_title_progress` (per-op channel)
    and the disc-level callback stays silent."""
    _stub_subprocess(
        monkeypatch,
        [
            'PRGT:5018,0,"Saving title #0 to MKV file"',
            "PRGV:5000,1000,10000",  # per-op 0.5, disc-overall 0.1
            "PRGV:10000,5000,10000",  # per-op 1.0, disc-overall 0.5
        ],
    )
    (tmp_path / "Disc_t00.mkv").write_bytes(b"x" * 64)

    title_progress: list[tuple[int, float]] = []
    disc_progress: list[float] = []

    async def on_title_start(_idx: int) -> None:
        return None

    async def on_title_progress(idx: int, frac: float) -> None:
        title_progress.append((idx, frac))

    async def on_disc_progress(frac: float) -> None:
        disc_progress.append(frac)

    result = await rip_disc(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        minlength_seconds=120,
        eligible_source_indexes=[0],
        on_title_start=on_title_start,
        on_title_progress=on_title_progress,
        on_disc_progress=on_disc_progress,
    )

    assert result.overall_error is None
    assert title_progress == [(0, 0.5), (0, 1.0)]
    assert disc_progress == []


@pytest.mark.asyncio
async def test_rip_disc_prgc_5017_fires_on_title_start_with_mapped_source_idx(monkeypatch, tmp_path):
    """PRGC:5017 is the primary per-title milestone in `mkv all` mode
    (confirmed against MakeMKV 1.18.3). The second field is the 0-based
    *output position* — it indexes into `eligible_source_indexes` to
    recover the source title index the dispatcher knows about.

    With a sparse eligible list (e.g. {3, 7} after some sub-minlength
    titles dropped), PRGC:5017,0 must fire `on_title_start(3)` and
    PRGC:5017,1 must fire `on_title_start(7)` — and PRGV between
    them must attribute progress to the right source index."""
    _stub_subprocess(
        monkeypatch,
        [
            'PRGT:5024,0,"Saving all titles to MKV files"',
            'PRGC:5017,0,"Saving to MKV file"',
            "PRGV:5000,1000,10000",  # per-op 0.5 of title at output pos 0
            'PRGC:5017,1,"Saving to MKV file"',
            "PRGV:9000,5000,10000",  # per-op 0.9 of title at output pos 1
            'MSG:5036,0,2,"Copy complete. 2 titles saved.","Copy complete. %1 %2","2","titles"',
        ],
    )
    (tmp_path / "Disc_t00.mkv").write_bytes(b"x" * 64)
    (tmp_path / "Disc_t01.mkv").write_bytes(b"y" * 64)

    starts: list[int] = []
    title_progress: list[tuple[int, float]] = []
    disc_progress: list[float] = []

    async def on_title_start(idx: int) -> None:
        starts.append(idx)

    async def on_title_progress(idx: int, frac: float) -> None:
        title_progress.append((idx, frac))

    async def on_disc_progress(frac: float) -> None:
        disc_progress.append(frac)

    result = await rip_disc(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        minlength_seconds=120,
        eligible_source_indexes=[3, 7],
        on_title_start=on_title_start,
        on_title_progress=on_title_progress,
        on_disc_progress=on_disc_progress,
    )

    assert result.overall_error is None
    # output positions 0,1 mapped via eligible_source_indexes → 3,7
    assert starts == [3, 7]
    # PRGV between PRGC:5017 events attributed to the active source idx
    assert title_progress == [(3, 0.5), (7, 0.9)]
    # disc-overall fallback never fires because PRGC:5017 set current_title
    assert disc_progress == []


@pytest.mark.asyncio
async def test_rip_disc_prgc_5017_out_of_range_position_is_skipped(monkeypatch, tmp_path):
    """If MakeMKV ever emits a PRGC:5017 with an output position past
    the eligible list (shouldn't happen, but mismatched scan/rip state
    could cause it), the streamer logs a warning and skips rather than
    crashing or attributing progress to a wrong track."""
    _stub_subprocess(
        monkeypatch,
        [
            'PRGT:5024,0,"Saving all titles to MKV files"',
            'PRGC:5017,5,"Saving to MKV file"',  # out of range — only 1 eligible
            "PRGV:5000,2500,10000",  # has no current_title → falls to disc-level
            'MSG:5036,0,2,"done","%1 %2","0","titles"',
        ],
    )

    starts: list[int] = []
    disc_progress: list[float] = []

    async def on_title_start(idx: int) -> None:
        starts.append(idx)

    async def on_disc_progress(frac: float) -> None:
        disc_progress.append(frac)

    result = await rip_disc(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        minlength_seconds=120,
        eligible_source_indexes=[0],
        on_title_start=on_title_start,
        on_disc_progress=on_disc_progress,
    )

    assert result.overall_error is None
    # No on_title_start fired — out-of-range was skipped.
    assert starts == []
    # current_title stayed None → PRGV fell through to disc-level callback.
    assert disc_progress == [0.25]


@pytest.mark.asyncio
async def test_rip_disc_fires_on_title_done_at_prgc_transitions(monkeypatch, tmp_path):
    """Mid-rip per-title finalisation. When PRGC:5017,N+1 fires (next
    title starts), the previous title's file is finalised on disk and
    the streamer fires `on_title_done(prev_source_idx)` before
    on_title_start for the new title — so the dispatcher can PATCH
    track N=DONE before track N+1 goes IN_PROGRESS."""
    _stub_subprocess(
        monkeypatch,
        [
            'PRGT:5024,0,"Saving all titles to MKV files"',
            'PRGC:5017,0,"Saving to MKV file"',
            "PRGV:10000,3000,10000",  # title 0 nearly done
            'PRGC:5017,1,"Saving to MKV file"',  # title 0 finalised → on_title_done(eligible[0])
            "PRGV:10000,7000,10000",  # title 1 nearly done
            'PRGC:5017,2,"Saving to MKV file"',  # title 1 finalised → on_title_done(eligible[1])
            'MSG:5036,0,2,"done","%1 %2","2","titles"',
        ],
    )
    (tmp_path / "Disc_t00.mkv").write_bytes(b"x" * 64)
    (tmp_path / "Disc_t01.mkv").write_bytes(b"y" * 64)
    (tmp_path / "Disc_t02.mkv").write_bytes(b"z" * 64)

    starts: list[int] = []
    dones: list[int] = []

    async def on_title_start(idx: int) -> None:
        starts.append(idx)

    async def on_title_done(idx: int) -> None:
        dones.append(idx)

    result = await rip_disc(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        minlength_seconds=120,
        eligible_source_indexes=[3, 7, 9],  # sparse to prove mapping
        on_title_start=on_title_start,
        on_title_done=on_title_done,
    )

    assert result.overall_error is None
    # All three titles started; all three finalised — first two via
    # PRGC transition, the last via clean-exit catch-up in rip_disc.
    assert starts == [3, 7, 9]
    assert dones == [3, 7, 9]


@pytest.mark.asyncio
async def test_rip_disc_fires_on_title_done_for_last_title_at_clean_exit(monkeypatch, tmp_path):
    """The last title in the rip never gets a follow-up PRGC:5017,N+1.
    rip_disc catches it with a final on_title_done sweep after the
    streamer drains and the process exits 0."""
    _stub_subprocess(
        monkeypatch,
        [
            'PRGT:5024,0,"Saving all titles to MKV files"',
            'PRGC:5017,0,"Saving to MKV file"',
            "PRGV:10000,10000,10000",
            'MSG:5036,0,2,"done","%1 %2","1","titles"',
        ],
    )
    (tmp_path / "Disc_t00.mkv").write_bytes(b"x" * 64)

    dones: list[int] = []

    async def on_title_done(idx: int) -> None:
        dones.append(idx)

    result = await rip_disc(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        minlength_seconds=120,
        eligible_source_indexes=[5],
        on_title_done=on_title_done,
    )

    assert result.overall_error is None
    assert dones == [5]


@pytest.mark.asyncio
async def test_rip_disc_on_title_done_fires_exactly_once_per_title(monkeypatch, tmp_path):
    """Defensive guard: PRGC:5017,N can fire repeatedly if MakeMKV
    re-emits a milestone (e.g. after a stream resync). on_title_done
    must fire exactly once per title regardless."""
    _stub_subprocess(
        monkeypatch,
        [
            'PRGT:5024,0,"Saving all titles to MKV files"',
            'PRGC:5017,0,"Saving to MKV file"',
            'PRGC:5017,0,"Saving to MKV file"',  # spurious repeat — must NOT trigger on_title_done(0)
            'PRGC:5017,1,"Saving to MKV file"',  # transitions off 0 → fires done(eligible[0])
            'MSG:5036,0,2,"done","%1 %2","2","titles"',
        ],
    )
    (tmp_path / "Disc_t00.mkv").write_bytes(b"x" * 64)
    (tmp_path / "Disc_t01.mkv").write_bytes(b"y" * 64)

    dones: list[int] = []

    async def on_title_done(idx: int) -> None:
        dones.append(idx)

    result = await rip_disc(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        minlength_seconds=120,
        eligible_source_indexes=[0, 1],
        on_title_done=on_title_done,
    )

    assert result.overall_error is None
    # eligible[0]=0 fires once at the 0→1 transition; eligible[1]=1 fires
    # once at clean-exit. Two dones total, no duplicates.
    assert dones == [0, 1]


@pytest.mark.asyncio
async def test_rip_disc_on_title_done_skipped_on_overall_failure(monkeypatch, tmp_path):
    """Non-zero exit aborts the rip; the final-title catch-up sweep is
    skipped so a half-written file isn't reported as DONE. The
    dispatcher's disc-error branch handles the FAILED transitions."""
    _stub_subprocess(
        monkeypatch,
        [
            'PRGT:5024,0,"Saving all titles to MKV files"',
            'PRGC:5017,0,"Saving to MKV file"',
            'MSG:1002,32,1,"LIBMKV_TRACE: Exception","LIBMKV_TRACE: %1","Exception"',
        ],
        returncode=1,
    )

    dones: list[int] = []

    async def on_title_done(idx: int) -> None:
        dones.append(idx)

    result = await rip_disc(
        device_path="/dev/sr0",
        output_dir=tmp_path,
        minlength_seconds=120,
        eligible_source_indexes=[0],
        on_title_done=on_title_done,
    )

    assert result.overall_error is not None
    # No on_title_done emissions on disc-level failure — caller marks tracks FAILED.
    assert dones == []


@pytest.mark.asyncio
async def test_rip_disc_returns_unavailable_when_makemkvcon_missing(monkeypatch, tmp_path):
    async def fake_create_subprocess_exec(*_args: Any, **_kwargs: Any):
        raise FileNotFoundError("makemkvcon")

    monkeypatch.setattr(makemkv_rip.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await rip_disc(device_path="/dev/sr0", output_dir=tmp_path)
    assert result.overall_error is not None
    assert "makemkvcon not on PATH" in result.overall_error
    assert result.titles == {}


@pytest.mark.asyncio
async def test_rip_disc_passes_minlength_to_makemkvcon(monkeypatch, tmp_path):
    """The CLI flag must be `--minlength=<int>` exactly — MakeMKV is
    strict about the equals form."""
    captured: dict[str, Any] = {}

    encoded = [b'MSG:5036,0,2,"done","%1 %2","0","titles"\n']
    fake = _FakeProc(encoded)

    async def fake_create_subprocess_exec(*args: Any, **_kwargs: Any) -> _FakeProc:
        captured["argv"] = args
        return fake

    monkeypatch.setattr(makemkv_rip.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    await rip_disc(device_path="/dev/sr0", output_dir=tmp_path, minlength_seconds=900)

    assert "--minlength=900" in captured["argv"]
    assert "all" in captured["argv"]
    # The output dir is the last positional after `all`.
    argv = list(captured["argv"])
    assert argv[argv.index("all") + 1] == str(tmp_path)


@pytest.mark.asyncio
async def test_msg_5021_surfaces_distinct_error_and_kills_proc(monkeypatch, tmp_path):
    """When MakeMKV emits MSG:5021 (binary kill-switch), rip_disc kills
    the subprocess from inside the streamer and returns a distinct
    `overall_error` that names the docs entry — so operators don't wait
    out the 6-hour RIP_TIMEOUT_SECONDS for a known upstream-blocked state.
    See docs/user/MakeMKV-Ripper.md § Failure modes."""
    _stub_subprocess(
        monkeypatch,
        [
            'MSG:1005,0,1,"MakeMKV v1.18.3 started","%1 started","..."',
            'MSG:5021,131332,1,"This application version is too old.","...","..."',
            # Lines after the kill must not be parsed — the streamer
            # short-circuits the loop and proc.kill() ends the stream.
            'PRGT:5024,0,"Saving all titles to MKV files"',
            "PRGV:5000,5000,10000",
            'MSG:5036,0,2,"Copy complete. 2 titles saved.","Copy complete.","2","titles"',
        ],
        returncode=1,
    )

    result = await rip_disc(
        device_path="iso:/fake/big.iso",
        output_dir=tmp_path,
        minlength_seconds=600,
        eligible_source_indexes=[0],
    )

    assert result.overall_error is not None
    assert "MSG:5021" in result.overall_error
    assert "docs/user/MakeMKV-Ripper.md" in result.overall_error
    assert result.titles == {}
    # The MSG:5021 line is preserved in the composed-error diagnostics so
    # operators can see the exact line that fired the guard.
    assert "131332" in result.overall_error


class _HangingProc(_FakeProc):
    """makemkvcon grinding against a dead device node: never exits on its own."""

    def __init__(self) -> None:
        super().__init__([])
        self._killed = asyncio.Event()
        self.killed = False

    async def wait(self) -> int:
        await self._killed.wait()
        return -9

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self._killed.set()


async def test_rip_disc_stop_kills_makemkvcon_and_reports_the_lost_drive(monkeypatch, tmp_path):
    """Once the caller sets `stop` (the drive dropped off the bus),
    makemkvcon is killed at once instead of failing title after title."""
    proc = _HangingProc()

    async def fake_create_subprocess_exec(*_args: Any, **_kwargs: Any) -> _FakeProc:
        return proc

    monkeypatch.setattr(makemkv_rip.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    stop = asyncio.Event()
    rip = asyncio.create_task(
        rip_disc(device_path="/dev/sr0", output_dir=tmp_path, eligible_source_indexes=[0, 1], stop=stop)
    )
    await asyncio.sleep(0.01)
    assert not rip.done()
    stop.set()
    result = await asyncio.wait_for(rip, timeout=2.0)
    assert proc.killed
    assert result.overall_error == makemkv_process.STOPPED_ERROR
    assert result.titles == {}


async def test_rip_disc_with_an_unset_stop_runs_to_completion(monkeypatch, tmp_path):
    _stub_subprocess(monkeypatch, ['MSG:5036,0,1,"Copy complete. 1 titles saved.","",""'])
    _write_title_file(tmp_path, 0)
    result = await rip_disc(
        device_path="/dev/sr0", output_dir=tmp_path, eligible_source_indexes=[0], stop=asyncio.Event()
    )
    assert result.overall_error is None
    assert result.titles[0].ok


_DIAG_LINE = 'MSG:1002,32,1,"LIBMKV_TRACE: Exception","LIBMKV_TRACE: %1","Exception"'


class _ScriptedHangingProc(_FakeProc):
    """Streams `lines`, then never exits until killed. Counts wait() calls;
    with `wait_raises_after_kill`, a wait() after the kill raises instead of returning."""

    def __init__(self, lines: list[str], *, wait_raises_after_kill: bool = False) -> None:
        super().__init__([(line + "\n").encode() for line in lines])
        self._killed = asyncio.Event()
        self.killed = False
        self.kill_count = 0
        self.waits_after_kill = 0
        self._raise_after_kill = wait_raises_after_kill

    async def wait(self) -> int:
        if self.killed:
            self.waits_after_kill += 1
            if self._raise_after_kill:
                raise RuntimeError("reap failed")
            return -9
        await self._killed.wait()
        self.waits_after_kill += 1
        return -9

    def kill(self) -> None:
        self.killed = True
        self.kill_count += 1
        self.returncode = -9
        self._killed.set()


def _spawn(monkeypatch, proc: _FakeProc) -> None:
    async def fake_create_subprocess_exec(*_args: Any, **_kwargs: Any) -> _FakeProc:
        return proc

    monkeypatch.setattr(makemkv_rip.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)


@pytest.mark.parametrize("with_stop", [False, True], ids=["no_stop", "stop_never_set"])
async def test_run_makemkvcon_timeout_kills_reaps_and_composes_the_error(monkeypatch, with_stop):
    """No `stop` goes through wait_for; an unset `stop` goes through asyncio.wait.
    Both end in the same kill, reap and composed timeout error."""
    monkeypatch.setattr(makemkv_process, "RIP_TIMEOUT_SECONDS", 0.02)
    proc = _ScriptedHangingProc([_DIAG_LINE])
    _spawn(monkeypatch, proc)
    state = makemkv_stream.ParserState()

    error = await makemkv_process.run_makemkvcon(["makemkvcon"], state, stop=asyncio.Event() if with_stop else None)

    assert state.diagnostics == ["LIBMKV_TRACE: Exception"]
    assert proc.killed
    assert proc.kill_count == 1
    assert proc.waits_after_kill >= 1
    assert error == makemkv_process.compose_error(
        f"makemkvcon timed out after {makemkv_process.RIP_TIMEOUT_SECONDS}s", state.diagnostics
    )
    assert error.endswith(": LIBMKV_TRACE: Exception")


async def test_run_makemkvcon_cancelled_swallows_a_reap_error_and_still_cancels(monkeypatch):
    proc = _ScriptedHangingProc([], wait_raises_after_kill=True)
    _spawn(monkeypatch, proc)
    task = asyncio.create_task(makemkv_process.run_makemkvcon(["makemkvcon"], makemkv_stream.ParserState()))
    await asyncio.sleep(0.01)
    assert not task.done()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert proc.killed
    assert proc.waits_after_kill == 1  # the reap ran, raised, and was swallowed


async def test_streamer_suspended_at_exit_is_cancelled_and_later_lines_are_dropped(monkeypatch):
    # Current behaviour, pinned for the guidelines refactor (#435): the cleanup cancels the streamer before
    # the drain. Filed as a defect.
    proc = _FakeProc(
        [
            (line + "\n").encode()
            for line in (
                _DIAG_LINE,
                'PRGT:5024,0,"Saving all titles to MKV files"',
                'PRGC:5017,0,"Saving to MKV file"',
                "PRGV:5000,1000,10000",  # on_title_progress suspends here
                'MSG:1002,32,1,"LIBMKV_TRACE: Late","LIBMKV_TRACE: %1","Late"',
                'PRGC:5017,1,"Saving to MKV file"',
            )
        ]
    )
    _spawn(monkeypatch, proc)
    state = makemkv_stream.ParserState()
    entered = asyncio.Event()
    never = asyncio.Event()

    async def on_title_progress(_idx: int, _frac: float) -> None:
        entered.set()
        await never.wait()

    error = await asyncio.wait_for(
        makemkv_process.run_makemkvcon(
            ["makemkvcon"],
            state,
            callbacks=makemkv_stream.RipCallbacks(on_title_progress=on_title_progress),
            eligible_source_indexes=[3, 7],
        ),
        timeout=2.0,
    )

    assert error is None
    assert entered.is_set()
    # Applied before the suspension.
    assert state.diagnostics == ["LIBMKV_TRACE: Exception"]
    assert state.current_title == 3
    # Dropped after it: the late diagnostic and the move to title 7.
    assert 7 not in state.titles


async def test_run_makemkvcon_nonzero_exit_without_stderr_reports_the_exit_code(monkeypatch):
    proc = _FakeProc([(_DIAG_LINE + "\n").encode()], returncode=3)
    proc.stderr = None  # type: ignore[assignment]
    _spawn(monkeypatch, proc)
    state = makemkv_stream.ParserState()

    error = await makemkv_process.run_makemkvcon(["makemkvcon"], state)

    assert state.diagnostics == ["LIBMKV_TRACE: Exception"]
    assert error == makemkv_process.compose_error("makemkvcon failed: exit=3", state.diagnostics)


async def test_rip_disc_captured_title_without_fail_reason_gets_the_generic_error_only_if_eligible(
    monkeypatch, tmp_path
):
    """A captured title (PRGT) with no file and no fail_reason adds nothing in the fail-reason loop:
    eligible -> the generic "no .mkv" error; not eligible -> absent."""
    _stub_subprocess(
        monkeypatch, ['PRGT:5018,0,"Saving title #4 to MKV file"', 'PRGT:5018,0,"Saving title #9 to MKV file"']
    )

    result = await rip_disc(device_path="/dev/sr0", output_dir=tmp_path, eligible_source_indexes=[4])

    assert result.overall_error is None
    assert set(result.titles) == {4}
    assert result.titles[4].ok is False
    assert result.titles[4].error == "makemkvcon exited 0 but produced no .mkv for this title"
    assert 9 not in result.titles


def _as_process(proc: _FakeProc) -> Any:
    return proc


async def test_wait_for_exit_without_stop_returns_false_when_the_proc_exits():
    assert await makemkv_process._wait_for_exit(_as_process(_FakeProc([])), None) is False


async def test_wait_for_exit_without_stop_times_out_when_the_proc_never_exits(monkeypatch):
    monkeypatch.setattr(makemkv_process, "RIP_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(asyncio.TimeoutError):
        await makemkv_process._wait_for_exit(_as_process(_HangingProc()), None)


async def test_wait_for_exit_with_stop_returns_false_when_the_proc_exits_first():
    assert await makemkv_process._wait_for_exit(_as_process(_FakeProc([])), asyncio.Event()) is False


async def test_wait_for_exit_returns_true_when_stop_is_set_first():
    stop = asyncio.Event()
    stop.set()
    assert await makemkv_process._wait_for_exit(_as_process(_HangingProc()), stop) is True


async def test_wait_for_exit_with_stop_times_out_when_neither_happens(monkeypatch):
    monkeypatch.setattr(makemkv_process, "RIP_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(asyncio.TimeoutError):
        await makemkv_process._wait_for_exit(_as_process(_HangingProc()), asyncio.Event())


async def test_kill_if_running_leaves_a_finished_proc_alone():
    proc = _ScriptedHangingProc([])
    proc.returncode = 0
    await subprocess_cleanup.kill_if_running(_as_process(proc))
    assert proc.kill_count == 0
    assert proc.waits_after_kill == 0


async def test_kill_if_running_kills_then_waits_for_a_running_proc():
    proc = _ScriptedHangingProc([])
    await subprocess_cleanup.kill_if_running(_as_process(proc))
    assert proc.kill_count == 1
    assert proc.waits_after_kill == 1


@pytest.mark.parametrize("error", [RuntimeError("reap failed"), asyncio.CancelledError()], ids=["exception", "cancel"])
async def test_kill_if_running_swallows_a_wait_that_raises(error):
    class _Proc(_FakeProc):
        async def wait(self) -> int:
            raise error

    proc = _Proc([])
    await subprocess_cleanup.kill_if_running(_as_process(proc))
    assert proc.returncode == -9


class _StderrStream:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


def _exited_proc(returncode: int, stderr: bytes | None) -> Any:
    proc = _FakeProc([], returncode=returncode)
    proc.returncode = returncode
    proc.stderr = None if stderr is None else _StderrStream(stderr)  # type: ignore[assignment]
    return proc


async def test_exit_error_binary_expired_wins_over_a_nonzero_exit():
    state = makemkv_stream.ParserState()
    state.binary_expired = True
    state.diagnostics.append("diag line")
    error = await makemkv_process._exit_error(_exited_proc(1, b"boom"), state)
    assert error is not None
    assert error.startswith("makemkvcon refused: binary is past its hard-coded expiry (MSG:5021).")
    assert error.endswith(": diag line")
    assert "boom" not in error


async def test_exit_error_clean_exit_is_none():
    assert await makemkv_process._exit_error(_exited_proc(0, b"ignored"), makemkv_stream.ParserState()) is None


async def test_exit_error_nonzero_reports_the_stripped_last_400_chars_of_stderr():
    stderr = b"HEAD" + b"x" * 500 + b"TAIL  \n"
    state = makemkv_stream.ParserState()
    error = await makemkv_process._exit_error(_exited_proc(1, stderr), state)
    assert error == makemkv_process.compose_error("makemkvcon failed: " + "x" * 396 + "TAIL", state.diagnostics)


@pytest.mark.parametrize("stderr", [b"", None], ids=["empty_stderr", "no_stderr"])
async def test_exit_error_nonzero_without_stderr_reports_the_exit_code(stderr):
    state = makemkv_stream.ParserState()
    error = await makemkv_process._exit_error(_exited_proc(3, stderr), state)
    assert error == makemkv_process.compose_error("makemkvcon failed: exit=3", state.diagnostics)


def test_mkv_all_command_for_a_device(tmp_path):
    assert makemkv_rip._mkv_all_command("/dev/sr0", tmp_path, 120) == [
        "makemkvcon",
        "mkv",
        "--robot",
        "--progress=-stdout",
        "--minlength=120",
        "dev:/dev/sr0",
        "all",
        str(tmp_path),
    ]


def test_mkv_all_command_for_an_iso_file(tmp_path):
    iso = tmp_path / "movie.iso"
    iso.write_bytes(b"")
    assert makemkv_rip._mkv_all_command(str(iso), tmp_path, 300) == [
        "makemkvcon",
        "mkv",
        "--robot",
        "--progress=-stdout",
        "--minlength=300",
        f"iso:{iso}",
        "all",
        str(tmp_path),
    ]


def test_mkv_all_command_has_all_exactly_once_right_before_the_output_dir(tmp_path):
    cmd = makemkv_rip._mkv_all_command("/dev/sr0", tmp_path, 120)
    assert cmd.count("all") == 1
    assert cmd[-2:] == ["all", str(tmp_path)]


def _pending_state(**titles: tuple[bool, bool]) -> makemkv_stream.ParserState:
    """Titles keyed `t<idx>` -> (started_emitted, done_emitted)."""
    state = makemkv_stream.ParserState()
    for name, (started, done) in titles.items():
        state.titles[int(name[1:])] = makemkv_stream._TitleState(started_emitted=started, done_emitted=done)
    return state


async def test_finish_pending_titles_emits_done_once_for_a_started_title():
    state = _pending_state(t3=(True, False))
    seen: list[int] = []

    async def on_done(idx: int) -> None:
        seen.append(idx)

    await makemkv_stream.finish_pending_titles(state, on_done)
    assert seen == [3]
    assert state.titles[3].done_emitted


async def test_finish_pending_titles_skips_done_and_never_started_titles():
    state = _pending_state(t1=(True, True), t2=(False, False))
    seen: list[int] = []

    async def on_done(idx: int) -> None:
        seen.append(idx)

    await makemkv_stream.finish_pending_titles(state, on_done)
    assert seen == []
    assert not state.titles[2].done_emitted


async def test_finish_pending_titles_emits_in_ascending_source_index_order():
    state = _pending_state(t5=(True, False), t0=(True, False), t2=(True, False))
    seen: list[int] = []

    async def on_done(idx: int) -> None:
        seen.append(idx)

    await makemkv_stream.finish_pending_titles(state, on_done)
    assert seen == [0, 2, 5]


async def test_finish_pending_titles_without_a_callback_still_marks_done():
    state = _pending_state(t1=(True, False))
    await makemkv_stream.finish_pending_titles(state, None)
    assert state.titles[1].done_emitted


async def test_attribute_outputs_pairs_eligible_indexes_with_files_in_rip_order(tmp_path):
    first = _write_title_file(tmp_path, 0, b"a" * 10)
    second = _write_title_file(tmp_path, 1, b"b" * 20)
    out = await makemkv_rip._attribute_outputs(tmp_path, [4, 7], hash_outputs=False)
    assert set(out) == {4, 7}
    assert out[4].ok and out[4].output_path == first and out[4].size_bytes == 10
    assert out[7].ok and out[7].output_path == second and out[7].size_bytes == 20


async def test_attribute_outputs_leaves_extra_files_unclaimed(tmp_path):
    _write_title_file(tmp_path, 0)
    _write_title_file(tmp_path, 1)
    out = await makemkv_rip._attribute_outputs(tmp_path, [3], hash_outputs=False)
    assert list(out) == [3]


async def test_attribute_outputs_omits_eligible_indexes_without_a_file(tmp_path):
    _write_title_file(tmp_path, 0)
    out = await makemkv_rip._attribute_outputs(tmp_path, [3, 5], hash_outputs=False)
    assert list(out) == [3]


async def test_attribute_outputs_hashes_when_asked(tmp_path):
    path = _write_title_file(tmp_path, 0, b"hash me")
    out = await makemkv_rip._attribute_outputs(tmp_path, [0], hash_outputs=True)
    assert out[0].sha256 == await makemkv_rip.sha256_file(path)
    assert out[0].sha256 is not None


async def test_attribute_outputs_leaves_sha256_unset_without_hashing(tmp_path):
    _write_title_file(tmp_path, 0)
    out = await makemkv_rip._attribute_outputs(tmp_path, [0], hash_outputs=False)
    assert out[0].sha256 is None


async def test_attribute_outputs_with_no_eligible_indexes_is_empty(tmp_path):
    _write_title_file(tmp_path, 0)
    assert await makemkv_rip._attribute_outputs(tmp_path, [], hash_outputs=True) == {}


def test_output_files_in_rip_order_skips_files_without_a_title_suffix(tmp_path):
    for name in ("disc_t01.mkv", "disc_t00.mkv", "stray.mkv", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    assert makemkv_rip.output_files_in_rip_order(tmp_path) == [tmp_path / "disc_t00.mkv", tmp_path / "disc_t01.mkv"]


def _state_with_reasons(**reasons: str | None) -> makemkv_stream.ParserState:
    """Titles keyed `t<idx>` -> fail_reason."""
    state = makemkv_stream.ParserState()
    for name, reason in reasons.items():
        state.titles[int(name[1:])] = makemkv_stream._TitleState(fail_reason=reason)
    return state


_NO_MKV = "makemkvcon exited 0 but produced no .mkv for this title"


def test_failed_titles_reports_a_captured_reason_for_an_unripped_title():
    out = makemkv_rip._failed_titles(_state_with_reasons(t2="read error"), [], {})
    assert out == {2: RipResult(ok=False, error="read error")}


def test_failed_titles_ignores_a_captured_reason_for_a_ripped_title():
    ripped = {2: RipResult(ok=True)}
    assert makemkv_rip._failed_titles(_state_with_reasons(t2="read error"), [], ripped) == {}


def test_failed_titles_without_a_reason_or_eligibility_gives_nothing():
    assert makemkv_rip._failed_titles(_state_with_reasons(t2=None), [], {}) == {}


def test_failed_titles_gives_the_generic_error_for_an_eligible_title_without_a_reason():
    out = makemkv_rip._failed_titles(makemkv_stream.ParserState(), [4], {})
    assert out == {4: RipResult(ok=False, error=_NO_MKV)}


def test_failed_titles_prefers_the_captured_reason_over_the_generic_error():
    out = makemkv_rip._failed_titles(_state_with_reasons(t4="read error"), [4], {})
    assert out == {4: RipResult(ok=False, error="read error")}


def test_failed_titles_orders_captured_reasons_before_generic_failures():
    ripped = {1: RipResult(ok=True)}
    state = _state_with_reasons(t9="bad", t3="worse")
    out = makemkv_rip._failed_titles(state, [8, 1, 3, 5], ripped)
    assert list(out) == [9, 3, 8, 5]


def test_failed_titles_does_not_mutate_ripped():
    ripped = {1: RipResult(ok=True)}
    makemkv_rip._failed_titles(_state_with_reasons(t2="bad"), [3], ripped)
    assert list(ripped) == [1]
