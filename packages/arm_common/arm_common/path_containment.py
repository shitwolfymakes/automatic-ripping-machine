"""`safe_join` / `is_within`: the one containment guard for a path built from
untrusted input (a request, a theme id, a name read off a disc). Both
resolve symlinks before the check, so a link inside the root that points
outward is caught, as are `..` and absolute names.
"""

from __future__ import annotations

from pathlib import Path


def _contained(resolved: Path, base: Path, allow_root: bool) -> bool:
    return allow_root if resolved == base else resolved.is_relative_to(base)


def is_within(path: Path, root: Path, *, allow_root: bool = False) -> bool:
    """True when `path` resolves inside `root`; `root` itself only with `allow_root`."""
    return _contained(path.resolve(), root.resolve(), allow_root)


def safe_join(base: Path, relative: str | Path, *, allow_root: bool = False) -> Path:
    """Join `relative` onto `base` and return the resolved path, proven inside `base`.

    Raises ValueError when the result lands outside `base` (`..`, an absolute
    name, an outward symlink), or is `base` itself unless `allow_root`.
    """
    base = base.resolve()
    target = (base / relative).resolve()
    if not _contained(target, base, allow_root):
        raise ValueError(f"path {str(relative)!r} escapes {base}")
    return target
