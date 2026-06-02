"""Sanitiser for human-readable path components.

The MusicBrainz lookup for a track titled `"Crown / She Said"` (a real
release on Collective Soul's *Dosage*) used to render
`Collective Soul/Dosage/11 - Crown / She Said - flac.flac`, which ffmpeg
interpreted as a non-existent subdirectory; every track in the queue
shared the artist/album path, so a single dirty title blocked the whole
session's transcodes. `sanitize_path_component` strips the separator
chars before they reach the path template.
"""

from __future__ import annotations

import pytest

from arm_backend.path_sanitize import sanitize_path_component


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Crown / She Said", "Crown - She Said"),
        ("AC/DC", "AC - DC"),
        ("foo\\bar", "foo - bar"),
        ("a/b\\c", "a - b - c"),
        # Windows / SMB illegal set, included so libraries shared across
        # hosts don't fall over: <>:"|?*
        ('Track "Live"', "Track - Live"),
        ("a:b", "a - b"),
        ("a|b", "a - b"),
        ("a?b", "a - b"),
        ("a*b", "a - b"),
        ("a<b>", "a - b"),
        # Embedded NUL — would break almost anything downstream.
        ("foo\x00bar", "foo - bar"),
        # Whitespace runs collapse + edges trim.
        ("  Hello   World  ", "Hello World"),
        # Trailing dots/spaces dropped (SMB strips silently).
        ("Album. ", "Album"),
        ("Album.", "Album"),
        # Empty string is a no-op (callers may pass empty when the
        # metadata isn't populated; template validation handles that).
        ("", ""),
        # Plain clean strings pass through unchanged.
        ("Collective Soul", "Collective Soul"),
        ("Dosage", "Dosage"),
        # Unicode preserved (no transliteration — that's what
        # `slugify` does, deliberately different).
        ("Sigur Rós", "Sigur Rós"),
    ],
)
def test_sanitize_path_component(raw: str, expected: str) -> None:
    assert sanitize_path_component(raw) == expected
