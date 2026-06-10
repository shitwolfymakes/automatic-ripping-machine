"""ISO ingress path sandboxing + filename metadata parse."""

import pytest

from arm_backend.iso_ingress import IngressError, parse_iso_filename, resolve_iso_path


def test_resolve_accepts_simple_path(tmp_path) -> None:
    iso = tmp_path / "Movie.iso"
    iso.write_bytes(b"x")
    resolved = resolve_iso_path(str(tmp_path), "Movie.iso")
    assert resolved == iso.resolve()


def test_resolve_rejects_parent_traversal(tmp_path) -> None:
    with pytest.raises(IngressError):
        resolve_iso_path(str(tmp_path), "../etc/passwd")


def test_resolve_rejects_absolute_path(tmp_path) -> None:
    with pytest.raises(IngressError):
        resolve_iso_path(str(tmp_path), "/etc/passwd")


def test_resolve_rejects_non_iso(tmp_path) -> None:
    (tmp_path / "movie.mkv").write_bytes(b"x")
    with pytest.raises(IngressError):
        resolve_iso_path(str(tmp_path), "movie.mkv")


def test_resolve_rejects_missing_file(tmp_path) -> None:
    with pytest.raises(IngressError):
        resolve_iso_path(str(tmp_path), "nope.iso")


def test_resolve_rejects_escaping_symlink(tmp_path) -> None:
    outside = tmp_path.parent / "outside.iso"
    outside.write_bytes(b"x")
    link = tmp_path / "link.iso"
    link.symlink_to(outside)
    with pytest.raises(IngressError):
        resolve_iso_path(str(tmp_path), "link.iso")


def test_parse_filename_title_and_year() -> None:
    title, year = parse_iso_filename("Iron Man (2008).iso")
    assert title == "Iron Man"
    assert year == 2008


def test_parse_filename_title_only() -> None:
    title, year = parse_iso_filename("Some_Disc.iso")
    assert title == "Some Disc"
    assert year is None
