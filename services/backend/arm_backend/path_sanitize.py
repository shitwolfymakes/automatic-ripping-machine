"""Sanitize metadata strings before they land in filesystem paths.

Distinct from `slugify`: this preserves human-readable case + spaces and is
only meant to make a single path component safe (no separator confusion, no
embedded NUL, no Windows-illegal trailing chars when the volume happens to
be a SMB mount). MusicBrainz titles like ``"Crown / She Said"`` or
``"AC/DC"`` reach the template engine verbatim; without sanitisation the
``/`` makes ffmpeg interpret the rendered path as a non-existent
subdirectory and the transcode silently fails on the first dispatch.
"""

import re

# Characters that would create or terminate a path segment. POSIX only
# truly forbids `/` and NUL; the others come from Windows/SMB compat —
# cheap to handle and keeps libraries shared across hosts portable.
_ILLEGAL = re.compile(r"[/\\\x00<>:\"|?*]")


def sanitize_path_component(value: str) -> str:
    """Make `value` safe as one path segment. Empty input passes through."""
    if not value:
        return value
    cleaned = _ILLEGAL.sub(" - ", value)
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Trim the artefacts of the sub: an illegal trailing char (`"`, `>`,
    # etc.) becomes ` - ` and looks like a dangling separator. Strip
    # any leading/trailing run of dash/dot/space so the output reads
    # naturally. Windows/SMB also drop trailing dots/spaces silently —
    # doing it here keeps the rendered path matching what lands on disk.
    return cleaned.strip(" -.")
