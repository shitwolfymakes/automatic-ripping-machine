"""Shared fixtures for the arm_common suite: the committed HandBrake schema dump and a Plex export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from arm_common.handbrake_schema.loader import load_schema
from arm_common.handbrake_schema.types import HandbrakeSchema
from arm_common.schemas.handbrake import HandbrakeSettings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def hb_raw() -> dict[str, Any]:
    """The raw libhb schema dump for HandBrake 1.11.1 (treat as read-only; deepcopy to mutate)."""
    return json.loads((FIXTURES / "handbrake-schema-1.11.1.json").read_text())


@pytest.fixture(scope="session")
def hb_schema(hb_raw: dict[str, Any]) -> HandbrakeSchema:
    return load_schema(hb_raw)


@pytest.fixture(scope="session")
def plex_export() -> Any:
    """A real GUI export of a custom Plex 720p preset."""
    return json.loads((FIXTURES / "handbrake-export-custom-plex-720p.json").read_text())


@pytest.fixture(scope="session")
def plex_settings() -> HandbrakeSettings:
    """The Plex export's settings as stored: common keys plus an nvenc_h264 block."""
    return HandbrakeSettings(
        common={
            "PictureWidth": 1280,
            "PictureHeight": 720,
            "VideoFramerateMode": "cfr",
            "AudioList": [{"AudioEncoder": "av_aac", "AudioMixdown": "5point1", "AudioBitrate": 384}],
        },
        encoders={
            "nvenc_h264": {
                "bit_depth": 8,
                "VideoPreset": "slower",
                "VideoProfile": "main",
                "VideoLevel": "4.0",
                "VideoQualitySlider": 18,
            }
        },
    )
