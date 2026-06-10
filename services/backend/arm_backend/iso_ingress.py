"""ISO ingress sandboxing + filename metadata heuristics.

Resolves an operator-supplied relative path under ISO_INGRESS_ROOT and proves
the real resolved path stays inside the root (defends against `..`, absolute
paths, and escaping symlinks). Mirrors the containment pattern used by the
logs/jobs path guards."""

import re
from pathlib import Path

_YEAR_RE = re.compile(r"\((\d{4})\)")


class IngressError(ValueError):
    """Requested ISO path is invalid, escapes the ingress root, or is absent."""


def resolve_iso_path(ingress_root: str, requested: str) -> Path:
    """Return the resolved absolute Path of `requested` under `ingress_root`.

    Raises IngressError on traversal/escape, non-.iso, or a missing file.
    """
    root = Path(ingress_root).resolve()
    if requested.startswith("/") or requested.startswith("\\"):
        raise IngressError("absolute paths are not allowed")
    candidate = (root / requested).resolve()
    # Containment: the resolved real path must be inside the root.
    if root != candidate and root not in candidate.parents:
        raise IngressError("path escapes the ingress root")
    if candidate.suffix.lower() != ".iso":
        raise IngressError("only .iso files are accepted")
    if not candidate.is_file():
        raise IngressError("file does not exist")
    return candidate


def parse_iso_filename(name: str) -> tuple[str, int | None]:
    """Best-effort title/year from an ISO filename. `Iron Man (2008).iso` ->
    ("Iron Man", 2008); underscores/dots become spaces."""
    stem = Path(name).stem
    year: int | None = None
    m = _YEAR_RE.search(stem)
    if m:
        year = int(m.group(1))
        stem = stem[: m.start()]
    title = re.sub(r"[._]+", " ", stem).strip()
    return title, year
