"""The shared config-singleton read."""

import asyncio

from arm_backend.config_row import load_config_or_none
from arm_common import Config
from tests._fakes import FakeSession


def test_returns_the_config_row() -> None:
    db = FakeSession()
    row = Config(id=1, transcode_enabled=False)
    db.rows["config"] = [row]
    assert asyncio.run(load_config_or_none(db)) is row  # type: ignore[arg-type]


def test_returns_none_before_the_row_is_seeded() -> None:
    db = FakeSession()
    db.rows["config"] = []
    assert asyncio.run(load_config_or_none(db)) is None  # type: ignore[arg-type]
