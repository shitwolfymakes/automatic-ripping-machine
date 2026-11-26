"""The HandBrake schema dump baked into the transcoder image.

The image build writes `HandBrakeCLI --preset-list`-derived schema JSON to
`/usr/share/arm/handbrake-schema.json`. The Backend runs this image with
`--dump-schema` to read it, and each transcoder reports its content hash when
it registers so the Backend can refuse a task whose image schema is stale.
"""

from __future__ import annotations

import functools
import json
import logging
import sys
from pathlib import Path
from typing import Any, TextIO

from arm_common.handbrake_schema.loader import content_hash, load_schema
from arm_common.handbrake_schema.types import HandbrakeSchema

logger = logging.getLogger(__name__)

BAKED_SCHEMA_PATH = Path("/usr/share/arm/handbrake-schema.json")


def _read_raw(path: Path) -> dict[str, Any]:
    """Parse the dump at `path`; raises OSError or ValueError when it cannot be read."""
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("schema dump is not a JSON object")
    return raw


def read_baked_raw(path: Path = BAKED_SCHEMA_PATH) -> dict[str, Any] | None:
    """The raw schema dump, or None (with a warning) when absent or unreadable."""
    try:
        return _read_raw(path)
    except (OSError, ValueError) as exc:
        logger.warning("no usable HandBrake schema at %s: %s", path, exc)
        return None


@functools.cache
def load_baked_schema(path: Path = BAKED_SCHEMA_PATH) -> HandbrakeSchema | None:
    """The parsed baked schema, cached per process; None when there is no usable dump."""
    raw = read_baked_raw(path)
    return None if raw is None else load_schema(raw)


def baked_schema_hash(path: Path = BAKED_SCHEMA_PATH) -> str | None:
    """Content hash of the baked dump, or None so an image without one registers like an old image."""
    raw = read_baked_raw(path)
    return None if raw is None else content_hash(raw)


def dump_schema(path: Path = BAKED_SCHEMA_PATH, out: TextIO = sys.stdout) -> int:
    """Print the baked dump as one compact JSON line; exit code 1 with a stderr line when unavailable."""
    if not path.exists():
        print(f"no HandBrake schema at {path}", file=sys.stderr)
        return 1
    try:
        raw = _read_raw(path)
    except (OSError, ValueError) as exc:
        print(f"unreadable HandBrake schema at {path}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(raw, separators=(",", ":")), file=out)
    return 0
