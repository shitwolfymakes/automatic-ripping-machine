"""7-Zip backed reader for UDF-only images."""

from __future__ import annotations

import subprocess

import pytest

from arm_ripper.scan import udf_image

_LISTING = """Path = BDMV
Folder = +
Size = 0

Path = BDMV/index.bdmv
Folder = -
Size = 466
Packed Size = 466

Path = BDMV/STREAM/00007.m2ts
Folder = -
Size = 20518293504
Packed Size = 20518293504

Path = BDMV/META/DL/bdmt_eng.xml
Folder = -
Size = 38316
Packed Size = 38316
"""


def test_parse_listing_keeps_files_with_sizes() -> None:
    assert udf_image.parse_listing(_LISTING) == [
        ("BDMV/index.bdmv", 466),
        ("BDMV/STREAM/00007.m2ts", 20518293504),
        ("BDMV/META/DL/bdmt_eng.xml", 38316),
    ]


def test_list_files_runs_7z(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(args, **_kw):  # type: ignore[no-untyped-def]
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=_LISTING.encode(), stderr=b"")

    monkeypatch.setattr(udf_image.shutil, "which", lambda _n: "/usr/bin/7z")
    monkeypatch.setattr(udf_image.subprocess, "run", fake_run)
    out = udf_image.list_files("/source/x.iso")
    assert out is not None and len(out) == 3
    assert calls[0][:3] == ["/usr/bin/7z", "l", "-slt"] and calls[0][-1] == "/source/x.iso"


def test_read_file_streams_one_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(args, **_kw):  # type: ignore[no-untyped-def]
        assert args[1:3] == ["e", "-so"] and args[-1] == "BDMV/META/DL/bdmt_eng.xml"
        return subprocess.CompletedProcess(args, 0, stdout=b"<xml/>", stderr=b"")

    monkeypatch.setattr(udf_image.shutil, "which", lambda _n: "/usr/bin/7z")
    monkeypatch.setattr(udf_image.subprocess, "run", fake_run)
    assert udf_image.read_file("/source/x.iso", "/BDMV/META/DL/bdmt_eng.xml") == b"<xml/>"


def test_without_7z_everything_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(udf_image.shutil, "which", lambda _n: None)
    assert udf_image.available() is False
    assert udf_image.list_files("/source/x.iso") is None
    assert udf_image.read_file("/source/x.iso", "a") is None


def test_7z_failure_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(args, **_kw):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args, 2, stdout=b"", stderr=b"Can not open the file as archive")

    monkeypatch.setattr(udf_image.shutil, "which", lambda _n: "/usr/bin/7z")
    monkeypatch.setattr(udf_image.subprocess, "run", fake_run)
    assert udf_image.list_files("/source/x.iso") is None
