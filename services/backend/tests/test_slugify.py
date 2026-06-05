import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.slugify import slugify  # noqa: E402


def test_lowercase_and_hyphenate() -> None:
    assert slugify("Plex 1080p H.265") == "plex-1080p-h-265"


def test_collapses_runs_of_punctuation() -> None:
    assert slugify("FLAC ___ 5.1") == "flac-5-1"


def test_strips_leading_trailing_hyphens() -> None:
    assert slugify("  -- hello --  ") == "hello"


def test_unicode_is_normalised() -> None:
    assert slugify("Café au lait") == "cafe-au-lait"


def test_empty_input() -> None:
    assert slugify("") == ""


def test_only_punctuation() -> None:
    assert slugify("!!!") == ""
