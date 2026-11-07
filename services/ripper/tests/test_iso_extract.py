"""ISO extract fallback: an image MakeMKV cannot open directly is unpacked with
7-Zip into scratch space under /raw and scanned/ripped as a disc folder
(`file:<dir>`), so it still shows its titles and rips as a movie instead of
being dumped whole.
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
import threading
from collections import namedtuple
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend.invalid")
os.environ.setdefault("ARM_SERVICE_TOKEN", "test-token")

import arm_ripper.extraction_routes as extraction_routes  # noqa: E402
import arm_ripper.iso_extract as iso_extract  # noqa: E402
import arm_ripper.scan.dispatcher as scan_dispatcher  # noqa: E402
from arm_common import DiscType, IsoPreparePhase  # noqa: E402
from arm_common.schemas import ScanResult  # noqa: E402
from arm_ripper.scan.makemkv import ScanError  # noqa: E402
from arm_ripper.source import makemkv_source_url  # noqa: E402

needs_7z = pytest.mark.skipif(shutil.which("7z") is None, reason="7z not installed")


def _udf_image(path: Path, video_dir: str | None = "BDMV") -> Path:
    """A tiny UDF 2.60 image, optionally carrying a video directory."""
    import pycdlib

    iso = pycdlib.PyCdlib()
    iso.new(udf="2.60")
    data = b"x" * 4096
    if video_dir is not None:
        iso.add_directory(f"/{video_dir[:8]}", udf_path=f"/{video_dir}")
        iso.add_fp(io.BytesIO(data), len(data), f"/{video_dir[:8]}/A.BIN;1", udf_path=f"/{video_dir}/a.bin")
    else:
        iso.add_fp(io.BytesIO(data), len(data), "/README.TXT;1", udf_path="/readme.txt")
    iso.write(str(path))
    iso.close()
    return path


@pytest.fixture(autouse=True)
async def _scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Path]:
    root = tmp_path / "raw" / ".iso-extract"
    monkeypatch.setattr(iso_extract, "EXTRACT_ROOT", root)
    await iso_extract.discard_all()
    yield root
    await iso_extract.discard_all()


class _Stream:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self, _n: int = -1) -> bytes:
        data, self._data = self._data, b""
        return data


class _Proc:
    """A finished 7z: empty progress on stdout, `stderr` on stderr."""

    def __init__(self, rc: int, stderr: bytes) -> None:
        self.returncode = rc
        self.stdout = _Stream(b"")
        self.stderr = _Stream(stderr)

    async def wait(self) -> int:
        return self.returncode


# --- extract ---------------------------------------------------------------


@needs_7z
async def test_extract_unpacks_a_video_image_and_routes_makemkv_to_the_folder(tmp_path: Path) -> None:
    iso = _udf_image(tmp_path / "The Movie.iso")

    root = await iso_extract.extract(str(iso))

    assert root is not None
    assert (root / "BDMV" / "a.bin").is_file()
    assert root.name == "The Movie"
    assert makemkv_source_url(str(iso)) == f"file:{root}/BDMV"


@needs_7z
async def test_extract_refuses_an_image_without_a_video_layout(tmp_path: Path, _scratch: Path) -> None:
    iso = _udf_image(tmp_path / "data.iso", video_dir=None)

    assert await iso_extract.extract(str(iso)) is None
    assert makemkv_source_url(str(iso)) == f"iso:{iso}"
    assert not any(_scratch.rglob("*"))  # the partial extraction is removed


async def test_extract_refuses_when_scratch_space_is_short(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    iso = tmp_path / "big.iso"
    iso.write_bytes(b"\0" * 10_000)
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(iso_extract.shutil, "disk_usage", lambda _p: usage(20_000, 15_000, 5_000))

    async def _no_7z(*_a: object, **_k: object) -> None:
        raise AssertionError("7z must not run without space for the extraction")

    monkeypatch.setattr(iso_extract.asyncio, "create_subprocess_exec", _no_7z)

    assert await iso_extract.extract(str(iso)) is None


@needs_7z
async def test_discard_all_removes_the_extraction(tmp_path: Path, _scratch: Path) -> None:
    iso = _udf_image(tmp_path / "m.iso")
    root = await iso_extract.extract(str(iso))
    assert root is not None

    await iso_extract.discard_all()

    assert not root.exists()
    assert makemkv_source_url(str(iso)) == f"iso:{iso}"


# --- scan dispatcher -------------------------------------------------------

_TITLE = {"index": 0, "duration_seconds": 5400, "size_bytes": 1, "chapter_count": 1}


def _patch_scan(
    monkeypatch: pytest.MonkeyPatch, *, rescan: ScanResult | None, extracted: Path | None
) -> dict[str, list[str]]:
    """MakeMKV fails on the image itself (`iso:`); the rescan (once the image
    is extracted, so the source URL is `file:`) answers `rescan`."""
    seen: dict[str, list[str]] = {"urls": [], "discarded": [], "discard_threads": []}

    async def _makemkv(device_path: str) -> ScanResult:
        url = makemkv_source_url(device_path)
        seen["urls"].append(url)
        if url.startswith("iso:") or rescan is None:
            raise ScanError("makemkvcon exited -11")
        return rescan

    async def _extract(path: str) -> Path | None:
        if extracted is not None:
            extraction_routes.route(path, extracted)
        return extracted

    async def _no_cd(_p: str) -> None:
        return None

    async def _data(_p: str) -> ScanResult:
        return ScanResult(disc_type=DiscType.BLURAY, volume_label="BD_LABEL")

    real_remove = iso_extract._remove_extractions

    def _remove(roots: list[Path]) -> None:
        seen["discarded"].append("all")
        seen["discard_threads"].append(threading.current_thread().name)
        real_remove(roots)

    monkeypatch.setattr(scan_dispatcher, "scan_makemkv", _makemkv)
    monkeypatch.setattr(scan_dispatcher.iso_extract, "extract", _extract)
    monkeypatch.setattr(iso_extract, "_remove_extractions", _remove)
    monkeypatch.setattr(scan_dispatcher, "scan_cd", _no_cd)
    monkeypatch.setattr(scan_dispatcher, "scan_data", _data)
    return seen


async def test_scan_rescues_an_unreadable_image_through_the_extracted_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    iso = tmp_path / "m.iso"
    iso.write_bytes(b"\0")
    folder = tmp_path / "m"
    (folder / "BDMV").mkdir(parents=True)
    rescan = ScanResult(disc_type=DiscType.BLURAY, volume_label="m", titles=[_TITLE])
    seen = _patch_scan(monkeypatch, rescan=rescan, extracted=folder)

    result = await scan_dispatcher.scan(str(iso))

    assert len(result.titles) == 1
    assert result.disc_type == DiscType.BLURAY
    # The image's own volume label wins over the scratch folder's name.
    assert result.volume_label == "BD_LABEL"
    assert seen["urls"] == [f"iso:{iso}", f"file:{folder}/BDMV"]
    assert seen["discarded"] == []


async def test_scan_discards_an_extraction_that_still_has_no_titles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    iso = tmp_path / "m.iso"
    iso.write_bytes(b"\0")
    seen = _patch_scan(monkeypatch, rescan=ScanResult(disc_type=DiscType.BLURAY, titles=[]), extracted=tmp_path / "m")

    result = await scan_dispatcher.scan(str(iso))

    assert result.titles == []
    assert result.disc_type == DiscType.BLURAY  # falls through to scan_data, as before
    assert seen["discarded"] == ["all"]
    # Removing a multi-GB extraction runs in a worker thread, not on the event loop.
    assert seen["discard_threads"] and "MainThread" not in seen["discard_threads"]
    assert makemkv_source_url(str(iso)) == f"iso:{iso}"


async def test_scan_never_extracts_a_device_node(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch_scan(monkeypatch, rescan=None, extracted=Path("/nowhere"))

    async def _boom(_p: str) -> Path | None:
        raise AssertionError("a device node must never be extracted")

    monkeypatch.setattr(scan_dispatcher.iso_extract, "extract", _boom)

    await scan_dispatcher.scan("/dev/sr0")

    assert seen["urls"] == ["dev:/dev/sr0"]


async def test_extract_runs_7zz_when_that_is_the_only_7zip_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Debian 12's `7zip` package (the ripper image's base) ships only `7zz`."""
    iso = tmp_path / "m.iso"
    iso.write_bytes(b"\0")
    monkeypatch.setattr(iso_extract.shutil, "which", lambda name: "/usr/bin/7zz" if name == "7zz" else None)
    argv: list[str] = []

    async def _exec(*args: str, **_k: object) -> _Proc:
        argv.extend(args)
        return _Proc(0, b"")

    monkeypatch.setattr(iso_extract.asyncio, "create_subprocess_exec", _exec)

    await iso_extract.extract(str(iso))

    assert argv[:2] == ["/usr/bin/7zz", "x"]


def _fake_7z(monkeypatch: pytest.MonkeyPatch, *, rc: int, stderr: bytes) -> None:
    """A 7z that writes a BDMV tree into its `-o` directory, then exits `rc`."""
    monkeypatch.setattr(iso_extract.shutil, "which", lambda name: "/usr/bin/7zz" if name == "7zz" else None)

    async def _exec(*args: str, **_k: object) -> _Proc:
        out = next(a for a in args if a.startswith("-o"))[2:]
        (Path(out) / "BDMV" / "STREAM").mkdir(parents=True)
        return _Proc(rc, stderr)

    monkeypatch.setattr(iso_extract.asyncio, "create_subprocess_exec", _exec)


async def test_extract_keeps_a_disc_whose_only_damage_is_outside_the_video_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DVDFab backups often carry unreadable CERTIFICATE / PS3_UPDATE files; 7z
    then exits 2, but MakeMKV never reads those."""
    iso = tmp_path / "MirrorMask.iso"
    iso.write_bytes(b"\0")
    _fake_7z(
        monkeypatch,
        rc=2,
        stderr=b"ERROR: Data Error : CERTIFICATE/id.bdmv\nERROR: Data Error : PS3_UPDATE/PS3UPDAT.PUP\n"
        b"ERROR: Data Error : PS3_VPRM/PARAM.SFO\n\nSub items Errors: 3\nArchives with Errors: 1\n",
    )

    root = await iso_extract.extract(str(iso))

    assert root is not None
    assert makemkv_source_url(str(iso)) == f"file:{root}/BDMV"


async def test_extract_drops_a_disc_with_damage_inside_the_video_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _scratch: Path
) -> None:
    iso = tmp_path / "m.iso"
    iso.write_bytes(b"\0")
    _fake_7z(
        monkeypatch,
        rc=2,
        stderr=b"ERROR: Data Error : CERTIFICATE/id.bdmv\nERROR: Data Error : BDMV/STREAM/00001.m2ts\n",
    )

    assert await iso_extract.extract(str(iso)) is None
    assert not any(_scratch.rglob("*"))


async def test_extract_drops_a_fatal_7z_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _scratch: Path
) -> None:
    iso = tmp_path / "m.iso"
    iso.write_bytes(b"\0")
    _fake_7z(monkeypatch, rc=2, stderr=b"ERROR: /source/m.iso\nCan not open the file as archive\n")

    assert await iso_extract.extract(str(iso)) is None


def test_a_rejected_extraction_logs_every_damaged_file(caplog: pytest.LogCaptureFixture) -> None:
    """The whole list, not the tail of 7z's stderr: a 300-character tail once
    showed only harmless CERTIFICATE files and hid 104 unreadable streams."""
    streams = [f"BDMV/STREAM/{i:05}.m2ts" for i in range(11, 120)]
    stderr = "\nERRORS:\nHeaders Error\nUnexpected end of archive\n\n" + "".join(
        f"ERROR: Data Error : {p}\n" for p in [*streams, "CERTIFICATE/id.bdmv"]
    )
    with caplog.at_level("ERROR", logger="arm_ripper.iso_extract"):
        assert iso_extract._usable(Path("m.iso"), 2, stderr) is False

    text = caplog.text
    assert "110 unreadable file(s)" in text
    assert "BDMV/STREAM/00011.m2ts" in text and "BDMV/STREAM/00119.m2ts" in text
    assert "Headers Error" in text and "Unexpected end of archive" in text


# --- _run_7z: no binary, timeout, cancellation -----------------------------


class _HangingStream:
    """A pipe that yields nothing until the process is killed, then hits EOF."""

    def __init__(self, killed: asyncio.Event) -> None:
        self._killed = killed

    async def read(self, _n: int = -1) -> bytes:
        await self._killed.wait()
        return b""


class _HangingProc:
    """A 7z that never finishes by itself: its stdout hangs until `kill`."""

    def __init__(self, *, kill_raises: bool = False) -> None:
        self._killed = asyncio.Event()
        self._kill_raises = kill_raises
        self.returncode = -9
        self.stdout = _HangingStream(self._killed)
        self.stderr = _Stream(b"")
        self.kill_calls = 0
        self.wait_calls = 0

    def kill(self) -> None:
        self.kill_calls += 1
        self._killed.set()
        if self._kill_raises:
            raise ProcessLookupError

    async def wait(self) -> int:
        self.wait_calls += 1
        return self.returncode


def _spawn_returns(monkeypatch: pytest.MonkeyPatch, proc: _HangingProc) -> None:
    monkeypatch.setattr(iso_extract.shutil, "which", lambda name: "/usr/bin/7z" if name == "7z" else None)

    async def _exec(*_a: object, **_k: object) -> _HangingProc:
        return proc

    monkeypatch.setattr(iso_extract.asyncio, "create_subprocess_exec", _exec)


async def test_run_7z_without_any_7zip_binary_logs_an_error_and_spawns_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(iso_extract.shutil, "which", lambda _name: None)

    async def _boom(*_a: object, **_k: object) -> None:
        raise AssertionError("nothing may be spawned without a 7-Zip binary")

    monkeypatch.setattr(iso_extract.asyncio, "create_subprocess_exec", _boom)

    with caplog.at_level("ERROR", logger="arm_ripper.iso_extract"):
        assert await iso_extract._run_7z(tmp_path / "m.iso", tmp_path / "out") is False

    assert [(r.levelname, r.getMessage()) for r in caplog.records] == [
        ("ERROR", "iso extract: 7-Zip (7z / 7zz) is not installed")
    ]


async def test_run_7z_timeout_kills_the_process_and_reraises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proc = _HangingProc()
    _spawn_returns(monkeypatch, proc)
    monkeypatch.setattr(iso_extract, "_EXTRACT_TIMEOUT_SECONDS", 0.05)

    with pytest.raises(TimeoutError):
        await iso_extract._run_7z(tmp_path / "m.iso", tmp_path / "out")

    assert proc.kill_calls == 1
    assert proc.wait_calls == 1


async def test_run_7z_suppresses_a_kill_on_an_already_exited_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = _HangingProc(kill_raises=True)
    _spawn_returns(monkeypatch, proc)
    monkeypatch.setattr(iso_extract, "_EXTRACT_TIMEOUT_SECONDS", 0.05)

    # The ProcessLookupError from kill() is swallowed; the timeout still surfaces.
    with pytest.raises(TimeoutError):
        await iso_extract._run_7z(tmp_path / "m.iso", tmp_path / "out")

    assert proc.kill_calls == 1
    assert proc.wait_calls == 1


async def test_run_7z_cancellation_kills_the_process_and_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = _HangingProc()
    _spawn_returns(monkeypatch, proc)
    task = asyncio.create_task(iso_extract._run_7z(tmp_path / "m.iso", tmp_path / "out"))
    await asyncio.sleep(0.01)  # let it spawn and block on the hanging pipe

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert proc.kill_calls == 1
    assert proc.wait_calls == 1


# --- extract: _run_7z raising ----------------------------------------------


@pytest.mark.parametrize("error", [asyncio.CancelledError(), RuntimeError("7z blew up")])
async def test_extract_removes_the_scratch_dir_when_run_7z_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _scratch: Path, error: BaseException
) -> None:
    iso = tmp_path / "m.iso"
    iso.write_bytes(b"\0" * 16)

    async def _raises(_image: Path, dest: Path) -> bool:
        (dest / "BDMV").mkdir()
        raise error

    monkeypatch.setattr(iso_extract, "_run_7z", _raises)

    with pytest.raises(type(error)):
        await iso_extract.extract(str(iso))

    assert not (_scratch / "drv_test").exists()
    assert extraction_routes.extracted_dir(str(iso)) is None


def test_find_7z_prefers_7z_and_never_asks_for_7zz(monkeypatch):
    asked: list[str] = []

    def _which(name: str) -> str | None:
        asked.append(name)
        return "/usr/bin/7z"

    monkeypatch.setattr(iso_extract.shutil, "which", _which)

    assert iso_extract._find_7z() == "/usr/bin/7z"
    assert asked == ["7z"]


def test_find_7z_falls_back_to_7zz(monkeypatch):
    monkeypatch.setattr(iso_extract.shutil, "which", lambda name: "/usr/bin/7zz" if name == "7zz" else None)

    assert iso_extract._find_7z() == "/usr/bin/7zz"


def test_find_7z_logs_an_error_and_returns_none_when_neither_is_installed(monkeypatch, caplog):
    monkeypatch.setattr(iso_extract.shutil, "which", lambda _name: None)

    with caplog.at_level("ERROR", logger="arm_ripper.iso_extract"):
        assert iso_extract._find_7z() is None

    assert [r.getMessage() for r in caplog.records] == ["iso extract: 7-Zip (7z / 7zz) is not installed"]


async def test_spawn_7z_starts_7zip_with_progress_and_errors_piped(monkeypatch, tmp_path):
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    sentinel = object()

    async def _exec(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(iso_extract.asyncio, "create_subprocess_exec", _exec)
    image, dest = tmp_path / "m.iso", tmp_path / "out"

    proc = await iso_extract._spawn_7z("/usr/bin/7z", image, dest)

    assert proc is sentinel
    assert calls == [
        (
            ("/usr/bin/7z", "x", "-tudf", "-y", "-bsp1", "-bso0", f"-o{dest}", "--", str(image)),
            {"stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE},
        )
    ]


class _ChunkStream:
    """Stands in for 7-Zip's stdout: each `read` hands back the next chunk, then b"" at the end."""

    def __init__(self, *chunks: bytes) -> None:
        self._chunks = list(chunks)

    async def read(self, _n: int) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""


async def _reports_for(monkeypatch: pytest.MonkeyPatch, *chunks: bytes) -> list[tuple[object, ...]]:
    reports: list[tuple[object, ...]] = []

    async def _report(*args: object) -> None:
        reports.append(args)

    monkeypatch.setattr(iso_extract.prepare, "report", _report)
    await iso_extract._report_progress(_ChunkStream(*chunks))  # type: ignore[arg-type]
    return reports


async def test_report_progress_reports_the_start_then_each_parsed_update(monkeypatch):
    reports = await _reports_for(monkeypatch, b" 12%\b\b\b", b" 75% 3 - BDMV/STREAM/00002.m2ts")

    assert reports == [
        (IsoPreparePhase.EXTRACTING, 0, None),
        (IsoPreparePhase.EXTRACTING, 12, None),
        (IsoPreparePhase.EXTRACTING, 75, "BDMV/STREAM/00002.m2ts"),
    ]


async def test_report_progress_reports_nothing_extra_for_a_chunk_without_progress(monkeypatch):
    reports = await _reports_for(monkeypatch, b"  0M Scan /source/\b\b\b")

    assert reports == [(IsoPreparePhase.EXTRACTING, 0, None)]


async def test_report_progress_parses_a_line_split_across_chunks_once_complete(monkeypatch):
    reports = await _reports_for(monkeypatch, b" 5", b"0% 1 - a.m2ts")

    assert reports == [
        (IsoPreparePhase.EXTRACTING, 0, None),
        (IsoPreparePhase.EXTRACTING, 50, "a.m2ts"),
    ]


async def test_report_progress_on_an_empty_stream_reports_only_the_start(monkeypatch):
    assert await _reports_for(monkeypatch) == [(IsoPreparePhase.EXTRACTING, 0, None)]


async def test_collect_7z_returns_stderr_of_a_finished_process(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _report(*_a: object) -> None:
        return None

    monkeypatch.setattr(iso_extract.prepare, "report", _report)
    proc = _HangingProc()
    proc.stdout = _Stream(b"")
    proc.stderr = _Stream(b"some warning")

    assert await iso_extract._collect_7z(proc) == b"some warning"  # type: ignore[arg-type]
    assert proc.wait_calls == 1
    assert proc.kill_calls == 0


async def test_collect_7z_timeout_kills_reaps_and_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _report(*_a: object) -> None:
        return None

    monkeypatch.setattr(iso_extract.prepare, "report", _report)
    monkeypatch.setattr(iso_extract, "_EXTRACT_TIMEOUT_SECONDS", 0.05)
    proc = _HangingProc()

    with pytest.raises(TimeoutError):
        await iso_extract._collect_7z(proc)  # type: ignore[arg-type]

    assert proc.kill_calls == 1
    assert proc.wait_calls == 1


def test_archive_errors_keeps_only_archive_level_lines_stripped_and_in_order() -> None:
    stderr = "\n".join(
        [
            "ERRORS:",
            "ERROR: Data Error : CERTIFICATE/id.bdmv",
            "",
            "   ",
            "  Can not open the file as archive",
            "ERROR: Disk full",
            "\tERROR: CRC Failed : BDMV/x.m2ts  ",
            "Unexpected end of archive",
        ]
    )

    assert iso_extract._archive_errors(stderr) == [
        "Can not open the file as archive",
        "ERROR: Disk full",
        "Unexpected end of archive",
    ]


def test_archive_errors_of_empty_stderr_is_empty() -> None:
    assert iso_extract._archive_errors("") == []


@pytest.mark.parametrize(
    ("damaged", "expected"),
    [
        ([], False),
        (["CERTIFICATE/id.bdmv", "PS3_UPDATE/PS3UPDAT.PUP"], True),
        (["BDMV/STREAM/00001.m2ts"], False),
        (["bdmv/STREAM/00001.m2ts"], False),
        (["VIDEO_TS/VTS_01_1.VOB"], False),
        (["id.bdmv"], True),
        (["CERTIFICATE/id.bdmv", "BDMV/STREAM/00001.m2ts"], False),
    ],
)
def test_damage_outside_video_tree(damaged: list[str], expected: bool) -> None:
    assert iso_extract._damage_outside_video_tree(damaged) is expected


def test_is_video_folder_accepts_a_bdmv_folder(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "BDMV").mkdir()

    with caplog.at_level("WARNING", logger="arm_ripper.iso_extract"):
        assert iso_extract._is_video_folder(Path("m.iso"), tmp_path) is True

    assert caplog.records == []


def test_is_video_folder_accepts_a_video_ts_folder(tmp_path: Path) -> None:
    (tmp_path / "VIDEO_TS").mkdir()

    assert iso_extract._is_video_folder(Path("m.iso"), tmp_path) is True


def test_is_video_folder_rejects_and_warns_when_neither_folder_exists(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING", logger="arm_ripper.iso_extract"):
        assert iso_extract._is_video_folder(Path("m.iso"), tmp_path) is False

    assert [(r.levelname, r.getMessage()) for r in caplog.records] == [
        ("WARNING", "iso extract: m.iso has no BDMV or VIDEO_TS folder; not a video disc")
    ]


def test_is_video_folder_rejects_a_regular_file_named_bdmv(tmp_path: Path) -> None:
    (tmp_path / "BDMV").write_text("not a folder")

    assert iso_extract._is_video_folder(Path("m.iso"), tmp_path) is False


async def test_extract_after_a_failed_7z_returns_none_without_checking_the_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, _scratch: Path
) -> None:
    iso = tmp_path / "m.iso"
    iso.write_bytes(b"\0")

    async def _failed(_image: Path, _dest: Path) -> bool:
        return False

    monkeypatch.setattr(iso_extract, "_run_7z", _failed)

    with caplog.at_level("WARNING", logger="arm_ripper.iso_extract"):
        assert await iso_extract.extract(str(iso)) is None

    assert not [r for r in caplog.records if "not a video disc" in r.getMessage()]
    assert not any(_scratch.rglob("*"))
