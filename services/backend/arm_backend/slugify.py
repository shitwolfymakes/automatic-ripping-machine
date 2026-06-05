"""Deterministic slug helper for `{transcode_slug}` token expansion.

NFKD-normalize, lowercase, collapse non-alphanumerics into single hyphens,
strip leading/trailing hyphens. Same rule documented in arch §02 path
templates.
"""

import re
import unicodedata


def slugify(s: str) -> str:
    norm = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")
