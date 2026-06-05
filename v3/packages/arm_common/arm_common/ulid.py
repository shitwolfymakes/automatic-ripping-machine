import re

from ulid import ULID

# Every id we mint is `<prefix>_<ULID>` — alphanumerics plus a single `_`
# separator, never a path separator, dot, or NUL. Several endpoints take an
# id as a URL path param and interpolate it straight into a filesystem path
# (per-job logs, `/raw/<job_id>/`), so this allowlist doubles as a
# path-traversal guard: a value that matches is a safe single path component
# and can neither contain `../` nor escape its parent dir. Kept deliberately
# looser than a strict ULID check so hand-written ids in tests still validate.
ID_COMPONENT_PATTERN = r"^[A-Za-z0-9_-]+$"
_ID_COMPONENT_RE = re.compile(ID_COMPONENT_PATTERN)


def new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


def is_safe_id_component(value: str) -> bool:
    """True if `value` is a single filesystem-safe path component.

    The matched charset has no `/`, `\\`, `.` or NUL, so any id that passes
    cannot traverse (`../`) or otherwise escape the directory it is joined to.
    Use as a guard wherever an externally-supplied id reaches a path.
    """
    return _ID_COMPONENT_RE.fullmatch(value) is not None
