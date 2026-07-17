from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from arm_backend.config import settings
from arm_common.schemas import DirectoryListing, FileEntry, FileRoot

# Code-resident roots registry. LOG is the fixed /logs mount (browse-only);
# the rest map to Settings path fields. Tests monkeypatch this dict.
ROOTS: dict[str, FileRoot] = {
    "MEDIA": FileRoot(key="MEDIA", label="Media", path=settings.MEDIA_ROOT, writable=True),
    "RAW": FileRoot(key="RAW", label="Raw rips", path=settings.RAW_ROOT, writable=True),
    "ISO": FileRoot(key="ISO", label="ISO ingress", path=settings.ISO_INGRESS_ROOT, writable=True),
    "LOG": FileRoot(key="LOG", label="Logs", path="/logs", writable=False),
}


class PathError(Exception):
    """Filesystem-operation error carrying a stable wire `code`."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def list_roots() -> list[FileRoot]:
    return list(ROOTS.values())


def _root(root_key: str) -> FileRoot:
    root = ROOTS.get(root_key)
    if root is None:
        raise PathError("unknown_root")
    return root


def resolve(root_key: str, subpath: str) -> Path:
    """Resolve (root_key, subpath) to an absolute path proven inside the root.

    Symlinks are collapsed by .resolve() BEFORE the containment check, so a
    symlink inside the root that points outward is rejected. A leading '/' or
    '..' that escapes the base is likewise caught.
    """
    base = Path(_root(root_key).path).resolve()
    target = (base / subpath).resolve()
    if target != base and not target.is_relative_to(base):
        raise PathError("path_escape")
    return target


def require_writable(root_key: str) -> None:
    if not _root(root_key).writable:
        raise PathError("read_only_root")


_CATEGORIES: dict[str, str] = {
    **{e: "video" for e in ("mkv", "mp4", "avi", "m2ts", "iso", "ts", "mov", "wmv")},
    **{e: "audio" for e in ("flac", "mp3", "wav", "aac", "ogg", "m4a")},
    **{e: "image" for e in ("png", "jpg", "jpeg", "gif", "webp", "bmp")},
    **{e: "subtitle" for e in ("srt", "sub", "ass", "ssa", "vtt")},
    **{e: "archive" for e in ("zip", "tar", "gz", "7z", "rar")},
    **{e: "document" for e in ("nfo", "txt", "json", "log", "xml")},
}


def categorize(extension: str | None) -> str:
    if extension is None:
        return "other"
    return _CATEGORIES.get(extension.lower(), "other")


def entry_for(path: Path) -> FileEntry:
    # Use lstat (follow_symlinks=False) so a dangling symlink child still
    # produces a valid entry instead of raising FileNotFoundError.
    st = path.stat(follow_symlinks=False)
    # Never classify a symlink as a directory — following it can fail or escape.
    is_dir = path.is_dir() and not path.is_symlink()
    ext = None if is_dir or "." not in path.name else path.name.rsplit(".", 1)[1].lower()
    return FileEntry(
        name=path.name,
        type="directory" if is_dir else "file",
        size=None if is_dir else st.st_size,
        modified=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        extension=ext,
        category=categorize(ext),
        permissions=oct(st.st_mode & 0o777)[2:],
    )


def list_dir(root_key: str, subpath: str) -> DirectoryListing:
    target = resolve(root_key, subpath)
    is_base = subpath in ("", "/")
    if not target.is_dir():
        # A configured-but-unmounted root (its own base dir is absent) degrades to
        # an empty `unavailable` listing so the UI can say "not mounted" instead of
        # erroring. A missing subpath WITHIN a mounted root is still a real 404.
        if is_base:
            return DirectoryListing(
                root=root_key,
                subpath=subpath,
                parent_subpath=None,
                readonly=not ROOTS[root_key].writable,
                entries=[],
                unavailable=True,
            )
        raise PathError("not_found")
    entries = [entry_for(p) for p in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))]
    if is_base:
        parent = None
    else:
        p = Path(subpath).parent
        parent = "" if p == Path(".") else str(p)
    return DirectoryListing(
        root=root_key,
        subpath=subpath,
        parent_subpath=parent,
        readonly=not ROOTS[root_key].writable,
        entries=entries,
        unavailable=False,
    )


def validate_name(name: str) -> None:
    if not name or "/" in name or name in (".", ".."):
        raise PathError("invalid_name")


def _subpath_of(root_key: str, target: Path) -> str:
    base = Path(ROOTS[root_key].path).resolve()
    rel = target.resolve().relative_to(base)
    return "" if str(rel) == "." else str(rel)


def make_dir(root_key: str, subpath: str, name: str) -> tuple[str, str]:
    require_writable(root_key)
    validate_name(name)
    parent = resolve(root_key, subpath)
    if not parent.is_dir():
        raise PathError("not_found")
    new = parent / name
    if new.exists():
        raise PathError("already_exists")
    new.mkdir()
    return root_key, _subpath_of(root_key, new)


def rename(root_key: str, subpath: str, new_name: str) -> tuple[str, str]:
    require_writable(root_key)
    validate_name(new_name)
    target = resolve(root_key, subpath)
    if not target.exists():
        raise PathError("not_found")
    dest = target.parent / new_name
    if dest.exists():
        raise PathError("already_exists")
    target.rename(dest)
    return root_key, _subpath_of(root_key, dest)


def move(root_key: str, subpath: str, dest_root: str, dest_subpath: str) -> tuple[str, str]:
    require_writable(root_key)
    dest_meta = ROOTS.get(dest_root)
    if dest_meta is None or not dest_meta.writable:
        raise PathError("dest_not_writable")
    src = resolve(root_key, subpath)
    if not src.exists():
        raise PathError("not_found")
    dest_dir = resolve(dest_root, dest_subpath)
    if not dest_dir.is_dir():
        raise PathError("not_found")
    # Reject moving a directory into itself or its own subtree.
    if src.is_dir() and (dest_dir == src or dest_dir.is_relative_to(src)):
        raise PathError("move_into_self")
    dest = dest_dir / src.name
    if dest.exists():
        raise PathError("already_exists")
    shutil.move(str(src), str(dest))
    return dest_root, _subpath_of(dest_root, dest)


def delete(root_key: str, subpath: str) -> None:
    require_writable(root_key)
    target = resolve(root_key, subpath)
    if not target.exists():
        raise PathError("not_found")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()


def fix_permissions(root_key: str, subpath: str) -> int:
    require_writable(root_key)
    target = resolve(root_key, subpath)
    if not target.exists():
        raise PathError("not_found")
    fixed = 0

    def _chmod(p: Path) -> None:
        nonlocal fixed
        # Skip symlinks entirely: os.chmod follows symlinks and would chmod the
        # target outside the sandbox.  A symlink's own mode is irrelevant.
        if p.is_symlink():
            return
        os.chmod(p, 0o755 if p.is_dir() else 0o644)
        fixed += 1

    _chmod(target)
    if target.is_dir():
        for p in target.rglob("*"):
            _chmod(p)
    return fixed
