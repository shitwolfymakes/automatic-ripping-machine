"""The BD disc title and matrix256 fall back to 7z for UDF-only images."""

from __future__ import annotations

import pytest

from arm_ripper.scan import bd_meta, matrix256_fp, udf_image

_BDMT = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<disclib xmlns:di="urn:BDA:bdmv;discinfo"><di:discinfo><di:title><di:name>MirrorMask</di:name></di:title>'
    b"<di:description><di:language>eng</di:language></di:description></di:discinfo></disclib>"
)


def _pycdlib_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    import pycdlib

    def _open(self, *_a, **_k):  # type: ignore[no-untyped-def]
        raise pycdlib.pycdlibexception.PyCdlibInvalidISO("Valid ISO9660 filesystems must have at least one PVD")

    monkeypatch.setattr(pycdlib.PyCdlib, "open", _open)


def test_bd_meta_uses_7z_when_pycdlib_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    _pycdlib_refuses(monkeypatch)
    monkeypatch.setattr(
        udf_image, "list_files", lambda _p: [("BDMV/index.bdmv", 466), ("BDMV/META/DL/bdmt_eng.xml", len(_BDMT))]
    )
    monkeypatch.setattr(udf_image, "read_file", lambda _p, inner: _BDMT if inner.endswith("bdmt_eng.xml") else None)
    meta = bd_meta.probe_bd_meta("/source/x.iso")
    assert meta is not None
    assert meta.name == "MirrorMask"


def test_bd_meta_none_when_7z_has_no_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    _pycdlib_refuses(monkeypatch)
    monkeypatch.setattr(udf_image, "list_files", lambda _p: [("BDMV/index.bdmv", 466)])
    assert bd_meta.probe_bd_meta("/source/x.iso") is None


def test_matrix256_uses_7z_records_when_pycdlib_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    _pycdlib_refuses(monkeypatch)
    records = [("BDMV/index.bdmv", 466), ("BDMV/STREAM/00007.m2ts", 20518293504)]
    monkeypatch.setattr(udf_image, "list_files", lambda _p: records)
    digest = matrix256_fp.probe_matrix256("/source/x.iso")
    assert digest == matrix256_fp.fingerprint_records(records)


def test_matrix256_none_when_7z_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _pycdlib_refuses(monkeypatch)
    monkeypatch.setattr(udf_image, "list_files", lambda _p: None)
    assert matrix256_fp.probe_matrix256("/source/x.iso") is None
