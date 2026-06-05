import re

from ulid import ULID

# A ULID renders as exactly 26 Crockford base32 chars (0-9 and A-Z minus the
# ambiguous I, L, O, U). Every id we mint is `<prefix>_<ULID>`; that charset
# has no path separator, dot, or NUL, so a value matching `id_pattern(prefix)`
# is always a single safe path component — these helpers double as the
# path-traversal guard for ids that reach the filesystem (per-job logs,
# `/raw/<job_id>/`).
_ULID_BODY = "[0-9A-HJKMNP-TV-Z]{26}"


def new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


def id_pattern(prefix: str) -> str:
    """Anchored regex matching `new_id(prefix)` output.

    Suitable both as a FastAPI path-param `pattern=` constraint and for a
    standalone `re` check (see `is_valid_id`).
    """
    return rf"^{re.escape(prefix)}_{_ULID_BODY}$"


def is_valid_id(prefix: str, value: str) -> bool:
    """True if `value` is a well-formed `new_id(prefix)` id.

    Because the ULID charset excludes `/`, `\\`, `.` and NUL, a value that
    passes can neither traverse (`../`) nor escape the directory it is joined
    to — use as a guard wherever an externally-supplied id reaches a path.
    """
    return re.fullmatch(id_pattern(prefix), value) is not None
