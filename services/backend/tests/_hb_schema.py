"""Shared HandBrake schema test data: the committed 1.11.1 dump, loaded once per process."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from arm_common.handbrake_schema.loader import load_schema
from arm_common.handbrake_schema.types import HandbrakeSchema

_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "arm_common"
    / "tests"
    / "fixtures"
    / "handbrake-schema-1.11.1.json"
)


@lru_cache(maxsize=1)
def fixture_raw() -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text())


@lru_cache(maxsize=1)
def fixture_schema() -> HandbrakeSchema:
    return load_schema(fixture_raw())


def schema_without_nvenc_h264_preset(name: str) -> HandbrakeSchema:
    """The fixture schema with `name` removed from the nvenc_h264 VideoPreset list."""
    raw = copy.deepcopy(fixture_raw())
    for encoder in raw["video_encoders"]:
        if encoder["name"] == "nvenc_h264":
            encoder["presets"] = [p for p in encoder["presets"] if p != name]
    return load_schema(raw)


def plex_export() -> dict[str, Any]:
    """A fresh copy of the committed GUI export of a custom Plex 720p preset."""
    path = _FIXTURE.parent / "handbrake-export-custom-plex-720p.json"
    return json.loads(path.read_text())
