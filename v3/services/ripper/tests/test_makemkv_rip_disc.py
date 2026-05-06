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

import arm_ripper.rip.makemkv_rip as makemkv_rip
from arm_ripper.rip.makemkv_rip import rip_disc


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
            'PRGT:0,5018,"Saving all titles to MKV files"',
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
            'PRGT:0,5018,"Saving all titles to MKV files"',
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
            'PRGT:0,5018,"Saving all titles to MKV files"',
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
            'PRGT:0,5018,"Saving all titles to MKV files"',
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
async def test_rip_disc_per_title_progress_takes_precedence_over_disc(monkeypatch, tmp_path):
    """When a per-title "Saving title #N" PRGT has identified the
    in-flight title, PRGV drives `on_title_progress` (per-op channel)
    and the disc-level callback stays silent — the per-title
    behaviour established in v2 is preserved unchanged."""
    _stub_subprocess(
        monkeypatch,
        [
            'PRGT:0,5018,"Saving title #0 to MKV file"',
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
