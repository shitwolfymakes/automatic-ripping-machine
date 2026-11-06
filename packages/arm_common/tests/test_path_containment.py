"""Path-containment guard: `safe_join` and `is_within`."""

from __future__ import annotations

from pathlib import Path

import pytest

from arm_common.path_containment import is_within, safe_join


def test_safe_join_returns_the_resolved_path_inside_base(tmp_path: Path) -> None:
    assert safe_join(tmp_path, "a/./b/../c.txt") == tmp_path.resolve() / "a" / "c.txt"


@pytest.mark.parametrize("relative", ["../x", "a/../../x", "/etc/passwd"])
def test_safe_join_rejects_a_path_outside_base(tmp_path: Path, relative: str) -> None:
    with pytest.raises(ValueError, match="escapes"):
        safe_join(tmp_path / "base", relative)


def test_safe_join_rejects_a_symlink_pointing_outward(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "link").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        safe_join(base, "link/x")


def test_safe_join_rejects_base_itself_unless_allowed(tmp_path: Path) -> None:
    for relative in ("", ".", "a/.."):
        with pytest.raises(ValueError, match="escapes"):
            safe_join(tmp_path, relative)
        assert safe_join(tmp_path, relative, allow_root=True) == tmp_path.resolve()


def test_safe_join_resolves_a_symlinked_base(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "alias").symlink_to(real)
    assert safe_join(tmp_path / "alias", "x") == real / "x"


def test_is_within(tmp_path: Path) -> None:
    assert is_within(tmp_path / "a" / "b", tmp_path)
    assert not is_within(tmp_path, tmp_path)
    assert is_within(tmp_path, tmp_path, allow_root=True)
    assert not is_within(tmp_path / ".." / "x", tmp_path)
    assert not is_within(tmp_path.parent, tmp_path, allow_root=True)
