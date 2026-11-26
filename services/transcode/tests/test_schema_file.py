"""Unit tests for arm_transcode.schema_file (the HandBrake schema baked into the image)."""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest

from arm_common.handbrake_schema.loader import content_hash
from arm_transcode import schema_file
from arm_transcode.schema_file import baked_schema_hash, dump_schema, load_baked_schema, read_baked_raw

FIXTURE = Path(__file__).parents[3] / "packages/arm_common/tests/fixtures/handbrake-schema-1.11.1.json"


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    load_baked_schema.cache_clear()


@pytest.fixture
def baked(tmp_path: Path) -> Path:
    target = tmp_path / "handbrake-schema.json"
    shutil.copy(FIXTURE, target)
    return target


def test_read_baked_raw_returns_the_parsed_dump(baked: Path) -> None:
    assert read_baked_raw(baked) == json.loads(FIXTURE.read_text())


def test_read_baked_raw_is_none_when_missing(tmp_path: Path) -> None:
    assert read_baked_raw(tmp_path / "absent.json") is None


def test_read_baked_raw_is_none_when_invalid(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert read_baked_raw(bad) is None


def test_load_baked_schema_parses_and_caches(baked: Path) -> None:
    first = load_baked_schema(baked)
    assert first is not None
    assert load_baked_schema(baked) is first


def test_load_baked_schema_is_none_when_missing(tmp_path: Path) -> None:
    assert load_baked_schema(tmp_path / "absent.json") is None


def test_baked_schema_hash_is_the_content_hash(baked: Path) -> None:
    assert baked_schema_hash(baked) == content_hash(json.loads(FIXTURE.read_text()))


def test_baked_schema_hash_is_none_when_missing(tmp_path: Path) -> None:
    assert baked_schema_hash(tmp_path / "absent.json") is None


def test_dump_schema_prints_one_compact_line(baked: Path) -> None:
    out = io.StringIO()
    assert dump_schema(baked, out) == 0
    assert out.getvalue().count("\n") == 1
    assert json.loads(out.getvalue()) == json.loads(FIXTURE.read_text())


def test_dump_schema_missing_file_reports_on_stderr(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "absent.json"
    out = io.StringIO()
    assert dump_schema(missing, out) == 1
    assert out.getvalue() == ""
    assert capsys.readouterr().err == f"no HandBrake schema at {missing}\n"


def test_dump_schema_unreadable_file_reports_the_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert dump_schema(bad, io.StringIO()) == 1
    assert capsys.readouterr().err.startswith(f"unreadable HandBrake schema at {bad}: ")


def test_default_path_is_the_image_location() -> None:
    assert schema_file.BAKED_SCHEMA_PATH == Path("/usr/share/arm/handbrake-schema.json")


def test_read_baked_raw_is_none_when_not_an_object(tmp_path: Path) -> None:
    arr = tmp_path / "arr.json"
    arr.write_text("[1]")
    assert read_baked_raw(arr) is None
