from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from arm_backend import file_browser as fb  # noqa: E402


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    media, raw, iso, log = (tmp_path / d for d in ("media", "raw", "iso", "log"))
    for d in (media, raw, iso, log):
        d.mkdir()
    from arm_common.schemas import FileRoot

    registry = {
        "MEDIA": FileRoot(key="MEDIA", label="Media", path=str(media), writable=True),
        "RAW": FileRoot(key="RAW", label="Raw", path=str(raw), writable=True),
        "ISO": FileRoot(key="ISO", label="ISO", path=str(iso), writable=True),
        "LOG": FileRoot(key="LOG", label="Logs", path=str(log), writable=False),
    }
    monkeypatch.setattr(fb, "ROOTS", registry)
    return {"MEDIA": media, "RAW": raw, "ISO": iso, "LOG": log}


def test_resolve_normal_subpath(roots):
    (roots["MEDIA"] / "movies").mkdir()
    assert fb.resolve("MEDIA", "movies") == (roots["MEDIA"] / "movies").resolve()


def test_resolve_empty_subpath_is_root(roots):
    assert fb.resolve("MEDIA", "") == roots["MEDIA"].resolve()


def test_resolve_unknown_root(roots):
    with pytest.raises(fb.PathError) as ei:
        fb.resolve("NOPE", "")
    assert ei.value.code == "unknown_root"


def test_resolve_dotdot_escape(roots):
    with pytest.raises(fb.PathError) as ei:
        fb.resolve("MEDIA", "../raw")
    assert ei.value.code == "path_escape"


def test_resolve_absolute_injection(roots):
    # An absolute subpath must not escape — joined then contained.
    with pytest.raises(fb.PathError) as ei:
        fb.resolve("MEDIA", "/etc")
    assert ei.value.code == "path_escape"


def test_resolve_symlink_escape(roots):
    outside = roots["MEDIA"].parent / "secret"
    outside.mkdir()
    (roots["MEDIA"] / "link").symlink_to(outside)
    with pytest.raises(fb.PathError) as ei:
        fb.resolve("MEDIA", "link")
    assert ei.value.code == "path_escape"


def test_require_writable_blocks_log(roots):
    with pytest.raises(fb.PathError) as ei:
        fb.require_writable("LOG")
    assert ei.value.code == "read_only_root"
    fb.require_writable("MEDIA")  # no raise


def test_list_roots(roots):
    keys = {r.key for r in fb.list_roots()}
    assert keys == {"MEDIA", "RAW", "ISO", "LOG"}


def test_categorize_known_and_unknown():
    assert fb.categorize("mkv") == "video"
    assert fb.categorize("flac") == "audio"
    assert fb.categorize("srt") == "subtitle"
    assert fb.categorize("png") == "image"
    assert fb.categorize("zip") == "archive"
    assert fb.categorize("nfo") == "document"
    assert fb.categorize(None) == "other"
    assert fb.categorize("xyz") == "other"


def test_list_dir_lists_entries(roots):
    (roots["MEDIA"] / "movies").mkdir()
    (roots["MEDIA"] / "a.mkv").write_bytes(b"x" * 5)
    dl = fb.list_dir("MEDIA", "")
    assert dl.root == "MEDIA" and dl.subpath == "" and dl.parent_subpath is None
    assert dl.readonly is False
    by_name = {e.name: e for e in dl.entries}
    assert by_name["movies"].type == "directory"
    assert by_name["a.mkv"].type == "file"
    assert by_name["a.mkv"].size == 5
    assert by_name["a.mkv"].extension == "mkv"
    assert by_name["a.mkv"].category == "video"
    assert by_name["a.mkv"].permissions is not None


def test_list_dir_parent_subpath(roots):
    (roots["MEDIA"] / "movies").mkdir()
    dl = fb.list_dir("MEDIA", "movies")
    assert dl.parent_subpath == ""


def test_list_dir_log_is_readonly(roots):
    dl = fb.list_dir("LOG", "")
    assert dl.readonly is True


def test_list_dir_missing(roots):
    with pytest.raises(fb.PathError) as ei:
        fb.list_dir("MEDIA", "nope")
    assert ei.value.code == "not_found"


def test_validate_name_rejects_bad(roots):
    for bad in ("", "a/b", ".", ".."):
        with pytest.raises(fb.PathError) as ei:
            fb.validate_name(bad)
        assert ei.value.code == "invalid_name"
    fb.validate_name("good name.mkv")  # no raise


def test_make_dir(roots):
    out = fb.make_dir("MEDIA", "", "movies")
    assert out == ("MEDIA", "movies")
    assert (roots["MEDIA"] / "movies").is_dir()


def test_make_dir_collision(roots):
    (roots["MEDIA"] / "movies").mkdir()
    with pytest.raises(fb.PathError) as ei:
        fb.make_dir("MEDIA", "", "movies")
    assert ei.value.code == "already_exists"


def test_make_dir_readonly_root(roots):
    with pytest.raises(fb.PathError) as ei:
        fb.make_dir("LOG", "", "x")
    assert ei.value.code == "read_only_root"


def test_rename(roots):
    (roots["MEDIA"] / "old.mkv").write_bytes(b"x")
    out = fb.rename("MEDIA", "old.mkv", "new.mkv")
    assert out == ("MEDIA", "new.mkv")
    assert (roots["MEDIA"] / "new.mkv").exists()
    assert not (roots["MEDIA"] / "old.mkv").exists()


def test_rename_collision(roots):
    (roots["MEDIA"] / "a").write_bytes(b"x")
    (roots["MEDIA"] / "b").write_bytes(b"y")
    with pytest.raises(fb.PathError) as ei:
        fb.rename("MEDIA", "a", "b")
    assert ei.value.code == "already_exists"


def test_move_across_roots(roots):
    (roots["RAW"] / "f.mkv").write_bytes(b"x")
    out = fb.move("RAW", "f.mkv", "MEDIA", "")
    assert out == ("MEDIA", "f.mkv")
    assert (roots["MEDIA"] / "f.mkv").exists()
    assert not (roots["RAW"] / "f.mkv").exists()


def test_move_dest_readonly(roots):
    (roots["MEDIA"] / "f").write_bytes(b"x")
    with pytest.raises(fb.PathError) as ei:
        fb.move("MEDIA", "f", "LOG", "")
    assert ei.value.code == "dest_not_writable"


def test_move_dest_unknown_root(roots):
    (roots["MEDIA"] / "f").write_bytes(b"x")
    with pytest.raises(fb.PathError) as ei:
        fb.move("MEDIA", "f", "NOPE", "")
    assert ei.value.code == "dest_not_writable"


def test_move_into_own_subtree(roots):
    (roots["MEDIA"] / "dir").mkdir()
    with pytest.raises(fb.PathError) as ei:
        fb.move("MEDIA", "dir", "MEDIA", "dir")
    assert ei.value.code == "move_into_self"


def test_move_collision(roots):
    (roots["RAW"] / "f").write_bytes(b"x")
    (roots["MEDIA"] / "f").write_bytes(b"y")
    with pytest.raises(fb.PathError) as ei:
        fb.move("RAW", "f", "MEDIA", "")
    assert ei.value.code == "already_exists"


def test_delete_file_and_tree(roots):
    (roots["MEDIA"] / "f.mkv").write_bytes(b"x")
    fb.delete("MEDIA", "f.mkv")
    assert not (roots["MEDIA"] / "f.mkv").exists()
    d = roots["MEDIA"] / "tree"
    (d / "sub").mkdir(parents=True)
    (d / "sub" / "g").write_bytes(b"y")
    fb.delete("MEDIA", "tree")
    assert not d.exists()


def test_delete_readonly_root(roots):
    with pytest.raises(fb.PathError) as ei:
        fb.delete("LOG", "anything")
    assert ei.value.code == "read_only_root"


def test_delete_missing(roots):
    with pytest.raises(fb.PathError) as ei:
        fb.delete("MEDIA", "nope")
    assert ei.value.code == "not_found"


def test_fix_permissions_counts(roots):
    d = roots["MEDIA"] / "d"
    (d / "sub").mkdir(parents=True)
    (d / "f.mkv").write_bytes(b"x")
    (d / "sub" / "g.mkv").write_bytes(b"y")
    import os as _os

    _os.chmod(d / "f.mkv", 0o600)
    n = fb.fix_permissions("MEDIA", "d")
    assert n == 4  # d, sub, f.mkv, g.mkv
    assert oct((d / "f.mkv").stat().st_mode & 0o777) == "0o644"
    assert oct((d / "sub").stat().st_mode & 0o777) == "0o755"


def test_make_dir_missing_parent_not_found(roots):
    with pytest.raises(fb.PathError) as ei:
        fb.make_dir("MEDIA", "missing_parent", "new_dir")
    assert ei.value.code == "not_found"


def test_rename_missing_not_found(roots):
    with pytest.raises(fb.PathError) as ei:
        fb.rename("MEDIA", "missing_file", "new_name")
    assert ei.value.code == "not_found"


def test_move_missing_source_not_found(roots):
    with pytest.raises(fb.PathError) as ei:
        fb.move("MEDIA", "missing_source", "RAW", "")
    assert ei.value.code == "not_found"


def test_move_dest_not_dir_not_found(roots):
    (roots["MEDIA"] / "source").write_bytes(b"x")
    (roots["RAW"] / "dest_file").write_bytes(b"y")
    with pytest.raises(fb.PathError) as ei:
        fb.move("MEDIA", "source", "RAW", "dest_file")
    assert ei.value.code == "not_found"


def test_fix_permissions_missing_not_found(roots):
    with pytest.raises(fb.PathError) as ei:
        fb.fix_permissions("MEDIA", "missing_target")
    assert ei.value.code == "not_found"


def test_fix_permissions_single_file(roots):
    f = roots["MEDIA"] / "test.mkv"
    f.write_bytes(b"x" * 10)
    import os as _os

    _os.chmod(f, 0o600)
    n = fb.fix_permissions("MEDIA", "test.mkv")
    assert n == 1
    assert oct(f.stat().st_mode & 0o777) == "0o644"


# ── C1: fix_permissions must NOT chmod through symlinks ──────────────────────


def test_fix_permissions_skips_symlink_target(tmp_path, roots):
    """A symlink inside a writable root must not have its TARGET chmod'd."""
    import os as _os

    # Victim file lives OUTSIDE the sandbox.
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"secret")
    _os.chmod(victim, 0o600)

    # Build a tree inside MEDIA with a real file, a real subdir, and a symlink.
    d = roots["MEDIA"] / "tree"
    sub = d / "sub"
    sub.mkdir(parents=True)
    real_file = d / "real.mkv"
    real_file.write_bytes(b"x")
    _os.chmod(real_file, 0o600)
    link = d / "escape_link"
    link.symlink_to(victim)

    n = fb.fix_permissions("MEDIA", "tree")

    # The outside victim must remain 0o600 (not chmod'd through the symlink).
    assert oct(victim.stat().st_mode & 0o777) == "0o600", "symlink target was chmod'd — escape!"

    # The symlink itself must NOT be counted in the fixed total.
    # Real entries: d (dir), sub (dir), real.mkv (file) → 3 entries.
    assert n == 3, f"expected 3 real entries fixed, got {n}"

    # Real files/dirs inside the tree should still get the right modes.
    assert oct(real_file.stat().st_mode & 0o777) == "0o644"
    assert oct(sub.stat().st_mode & 0o777) == "0o755"


# ── I1a: list_dir must tolerate dangling symlinks ────────────────────────────


def test_list_dir_dangling_symlink(roots):
    """A dangling symlink child must not crash list_dir; it appears as type 'file'."""
    d = roots["MEDIA"] / "has_dangling"
    d.mkdir()
    dangling = d / "gone_link"
    dangling.symlink_to(d / "nonexistent_target")

    # Must not raise.
    listing = fb.list_dir("MEDIA", "has_dangling")
    by_name = {e.name: e for e in listing.entries}
    assert "gone_link" in by_name, "dangling symlink entry missing from listing"
    assert by_name["gone_link"].type == "file", "dangling symlink should be reported as 'file'"


def test_list_dir_missing_root_base_unavailable(roots, tmp_path, monkeypatch):
    """A configured-but-unmounted root (base dir absent) lists as empty +
    unavailable instead of raising not_found — so the UI shows 'not mounted'."""
    from arm_common.schemas import FileRoot

    ghost = tmp_path / "ghost"  # never created
    registry = {**fb.ROOTS, "GHOST": FileRoot(key="GHOST", label="Ghost", path=str(ghost), writable=True)}
    monkeypatch.setattr(fb, "ROOTS", registry)
    listing = fb.list_dir("GHOST", "")
    assert listing.unavailable is True
    assert listing.entries == []
    assert listing.parent_subpath is None


def test_list_dir_existing_root_not_unavailable(roots):
    """A mounted root lists normally with unavailable False."""
    listing = fb.list_dir("MEDIA", "")
    assert listing.unavailable is False
