from __future__ import annotations


from pathlib import Path

import pytest

from arm_backend import file_browser as fb


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
        "STAGING": FileRoot(key="STAGING", label="Staging", path=str(raw / ".staging"), writable=False),
        "LOG": FileRoot(key="LOG", label="Logs", path=str(log), writable=False),
    }
    monkeypatch.setattr(fb, "ROOTS", registry)
    return {"MEDIA": media, "RAW": raw, "ISO": iso, "LOG": log, "STAGING": raw / ".staging"}


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
    assert keys == {"MEDIA", "RAW", "ISO", "LOG", "STAGING"}


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


# ── fix_permissions must NOT chmod through symlinks ──────────────────────


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


# --- D49(b): read-only STAGING root; RAW hides and protects the staging folder ---


@pytest.fixture
def staged(roots):
    st = roots["STAGING"]
    (st / "job1").mkdir(parents=True)
    (st / "job1" / "t.mkv").write_bytes(b"x")
    (roots["RAW"] / "rip").mkdir()
    (roots["RAW"] / ".other").mkdir()
    return roots


def test_staging_root_is_listed_read_only(staged):
    root = next(r for r in fb.list_roots() if r.key == "STAGING")
    assert root.writable is False
    listing = fb.list_dir("STAGING", "")
    assert listing.readonly is True
    assert [e.name for e in listing.entries] == ["job1"]
    assert [e.name for e in fb.list_dir("STAGING", "job1").entries] == ["t.mkv"]


@pytest.mark.parametrize(
    "call",
    [
        lambda: fb.make_dir("STAGING", "", "x"),
        lambda: fb.rename("STAGING", "job1", "x"),
        lambda: fb.delete("STAGING", "job1"),
        lambda: fb.move("STAGING", "job1", "MEDIA", ""),
        lambda: fb.fix_permissions("STAGING", "job1"),
    ],
)
def test_staging_root_refuses_every_write(staged, call):
    with pytest.raises(fb.PathError) as ei:
        call()
    assert ei.value.code == "read_only_root"
    assert (staged["STAGING"] / "job1" / "t.mkv").exists()


def test_raw_listing_hides_only_the_staging_folder(staged):
    names = [e.name for e in fb.list_dir("RAW", "").entries]
    assert names == [".other", "rip"]


@pytest.mark.parametrize(
    "call",
    [
        lambda: fb.delete("RAW", ".staging/job1"),
        lambda: fb.delete("RAW", ".staging"),
        lambda: fb.rename("RAW", ".staging", "gone"),
        lambda: fb.rename("RAW", ".staging/job1", "x"),
        lambda: fb.make_dir("RAW", ".staging", "x"),
        lambda: fb.make_dir("RAW", ".staging/job1", "x"),
        lambda: fb.move("RAW", ".staging/job1", "MEDIA", ""),
        lambda: fb.move("RAW", "rip", "RAW", ".staging/job1"),
        lambda: fb.fix_permissions("RAW", ".staging/job1"),
        lambda: fb.delete("RAW", "rip/../.staging/job1"),
        lambda: fb.delete("RAW", ""),
    ],
)
def test_raw_writes_into_staging_are_refused(staged, call):
    with pytest.raises(fb.PathError) as ei:
        call()
    assert ei.value.code == "staging_protected"
    assert (staged["STAGING"] / "job1" / "t.mkv").exists()


def test_raw_writes_outside_staging_still_work(staged):
    fb.make_dir("RAW", "", "new")
    fb.rename("RAW", "new", "newer")
    fb.delete("RAW", "newer")
    fb.fix_permissions("RAW", "rip")
    assert not (staged["RAW"] / "newer").exists()


def test_raw_symlink_into_staging_is_refused(staged):
    (staged["RAW"] / "alias").symlink_to(staged["STAGING"] / "job1")
    with pytest.raises(fb.PathError) as ei:
        fb.delete("RAW", "alias")
    assert ei.value.code == "staging_protected"


def test_separate_staging_leaves_raw_untouched(staged, monkeypatch, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.setitem(fb.ROOTS, "STAGING", fb.ROOTS["STAGING"].model_copy(update={"path": str(other)}))
    assert [e.name for e in fb.list_dir("RAW", "").entries] == [".other", ".staging", "rip"]
    fb.delete("RAW", ".staging/job1")


def test_no_staging_root_registered_means_nothing_is_protected(staged, monkeypatch):
    monkeypatch.delitem(fb.ROOTS, "STAGING")
    fb.delete("RAW", ".staging/job1")


def test_staging_path_predicates(tmp_path):
    st = tmp_path / "raw" / ".staging"
    assert fb.inside_staging(st, st) and fb.inside_staging(st / "a", st)
    assert not fb.inside_staging(tmp_path / "raw", st)
    assert fb.contains_staging(tmp_path / "raw", st) and fb.contains_staging(st / "a", st)
    assert not fb.contains_staging(tmp_path / "raw" / "other", st)


def test_real_registry_lists_staging_read_only_at_the_configured_staging_root():
    from arm_backend.config import settings, staging_root

    root = fb.ROOTS["STAGING"]
    assert (root.label, root.writable, root.path) == ("Staging", False, str(staging_root(settings)))
