"""ISO extract fallback: an image MakeMKV cannot open directly is unpacked with
7-Zip into scratch space under /raw and scanned/ripped as a disc folder
(`file:<dir>`), so it still shows its titles and rips as a movie instead of
being dumped whole.
"""

from __future__ import annotations

import io
import os
import shutil
from collections import namedtuple
from pathlib import Path

import pytest

os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend.invalid")
os.environ.setdefault("ARM_SERVICE_TOKEN", "test-token")

import arm_ripper.iso_extract as iso_extract  # noqa: E402
import arm_ripper.scan.dispatcher as scan_dispatcher  # noqa: E402
from arm_common import DiscType  # noqa: E402
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
def _scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "raw" / ".iso-extract"
    monkeypatch.setattr(iso_extract, "EXTRACT_ROOT", root)
    iso_extract.discard_all()
    yield root
    iso_extract.discard_all()


# --- extract ---------------------------------------------------------------


@needs_7z
async def test_extract_unpacks_a_video_image_and_routes_makemkv_to_the_folder(tmp_path: Path) -> None:
    iso = _udf_image(tmp_path / "The Movie.iso")

    root = await iso_extract.extract(str(iso))

    assert root is not None
    assert (root / "BDMV" / "a.bin").is_file()
    assert root.name == "The Movie"
    assert makemkv_source_url(str(iso)) == f"file:{root}"


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

    iso_extract.discard_all()

    assert not root.exists()
    assert makemkv_source_url(str(iso)) == f"iso:{iso}"


# --- scan dispatcher -------------------------------------------------------

_TITLE = {"index": 0, "duration_seconds": 5400, "size_bytes": 1, "chapter_count": 1}


def _patch_scan(
    monkeypatch: pytest.MonkeyPatch, *, rescan: ScanResult | None, extracted: Path | None
) -> dict[str, list[str]]:
    """MakeMKV fails on the image itself (`iso:`); the rescan (once the image
    is extracted, so the source URL is `file:`) answers `rescan`."""
    seen: dict[str, list[str]] = {"urls": [], "discarded": []}

    async def _makemkv(device_path: str) -> ScanResult:
        url = makemkv_source_url(device_path)
        seen["urls"].append(url)
        if url.startswith("iso:") or rescan is None:
            raise ScanError("makemkvcon exited -11")
        return rescan

    async def _extract(path: str) -> Path | None:
        if extracted is not None:
            iso_extract._extracted[path] = extracted
        return extracted

    async def _no_cd(_p: str) -> None:
        return None

    async def _data(_p: str) -> ScanResult:
        return ScanResult(disc_type=DiscType.BLURAY, volume_label="BD_LABEL")

    real_discard = iso_extract.discard_all

    def _discard() -> None:
        seen["discarded"].append("all")
        real_discard()

    monkeypatch.setattr(scan_dispatcher, "scan_makemkv", _makemkv)
    monkeypatch.setattr(scan_dispatcher.iso_extract, "extract", _extract)
    monkeypatch.setattr(scan_dispatcher.iso_extract, "discard_all", _discard)
    monkeypatch.setattr(scan_dispatcher, "scan_cd", _no_cd)
    monkeypatch.setattr(scan_dispatcher, "scan_data", _data)
    return seen


async def test_scan_rescues_an_unreadable_image_through_the_extracted_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    iso = tmp_path / "m.iso"
    iso.write_bytes(b"\0")
    folder = tmp_path / "m"
    rescan = ScanResult(disc_type=DiscType.BLURAY, volume_label="m", titles=[_TITLE])
    seen = _patch_scan(monkeypatch, rescan=rescan, extracted=folder)

    result = await scan_dispatcher.scan(str(iso))

    assert len(result.titles) == 1
    assert result.disc_type == DiscType.BLURAY
    # The image's own volume label wins over the scratch folder's name.
    assert result.volume_label == "BD_LABEL"
    assert seen["urls"] == [f"iso:{iso}", f"file:{folder}"]
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
    assert makemkv_source_url(str(iso)) == f"iso:{iso}"


async def test_scan_never_extracts_a_device_node(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch_scan(monkeypatch, rescan=None, extracted=Path("/nowhere"))

    async def _boom(_p: str) -> Path | None:
        raise AssertionError("a device node must never be extracted")

    monkeypatch.setattr(scan_dispatcher.iso_extract, "extract", _boom)

    await scan_dispatcher.scan("/dev/sr0")

    assert seen["urls"] == ["dev:/dev/sr0"]
