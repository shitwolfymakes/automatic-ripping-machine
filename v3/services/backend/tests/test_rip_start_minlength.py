"""rip-start resolves Session.overrides_json["min_length_seconds"] and
threads it through `RipStartResponse.min_length_seconds`. The ripper
falls back to its host-side `ARM_MIN_LENGTH_SECONDS` baseline when the
field is None — so we explicitly test:

  - No pending_session_id → None
  - pending_session_id with no overrides → None
  - pending_session_id with overrides_json["min_length_seconds"]=N → N
  - Bogus override (string, bool, negative) → None (defensive)
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend.routers.ripper import _resolve_min_length_override  # noqa: E402
from arm_common import (  # noqa: E402
    DiscType,
    Job,
    JobStatus,
    MediaType,
    Session,
)

from tests._fakes import FakeSession  # noqa: E402


def _make_job(metadata_json: dict | None = None) -> Job:
    return Job(
        id="job_x",
        drive_id="drv_x",
        disc_type=DiscType.BLURAY,
        title=None,
        year=None,
        status=JobStatus.IDENTIFIED,
        metadata_json=metadata_json or {},
    )


def _make_session(overrides_json: dict | None) -> Session:
    return Session(
        id="ses_x",
        name="My Session",
        media_type=MediaType.MOVIE,
        is_builtin=False,
        rip_preset_id="rpr_x",
        transcode_preset_id=None,
        output_path_template="{title}.{ext}",
        overrides_json=overrides_json,
    )


@pytest.mark.asyncio
async def test_no_pending_session_returns_none() -> None:
    db = FakeSession()
    job = _make_job(metadata_json={})
    result = await _resolve_min_length_override(db, job)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.asyncio
async def test_pending_session_without_overrides_returns_none() -> None:
    db = FakeSession()
    db.rows["sessions"] = [_make_session(overrides_json=None)]
    job = _make_job(metadata_json={"pending_session_id": "ses_x"})
    result = await _resolve_min_length_override(db, job)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.asyncio
async def test_session_overrides_min_length() -> None:
    db = FakeSession()
    db.rows["sessions"] = [_make_session(overrides_json={"min_length_seconds": 1200})]
    job = _make_job(metadata_json={"pending_session_id": "ses_x"})
    result = await _resolve_min_length_override(db, job)  # type: ignore[arg-type]
    assert result == 1200


@pytest.mark.asyncio
async def test_session_overrides_with_unrelated_keys_only_returns_none() -> None:
    db = FakeSession()
    db.rows["sessions"] = [_make_session(overrides_json={"some_other_key": "x"})]
    job = _make_job(metadata_json={"pending_session_id": "ses_x"})
    result = await _resolve_min_length_override(db, job)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.asyncio
async def test_string_value_rejected() -> None:
    db = FakeSession()
    db.rows["sessions"] = [_make_session(overrides_json={"min_length_seconds": "600"})]
    job = _make_job(metadata_json={"pending_session_id": "ses_x"})
    result = await _resolve_min_length_override(db, job)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.asyncio
async def test_bool_value_rejected() -> None:
    """bool is an int subclass in Python — without the explicit guard,
    `True` would resolve to `1`. Reject explicitly."""
    db = FakeSession()
    db.rows["sessions"] = [_make_session(overrides_json={"min_length_seconds": True})]
    job = _make_job(metadata_json={"pending_session_id": "ses_x"})
    result = await _resolve_min_length_override(db, job)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.asyncio
async def test_negative_value_rejected() -> None:
    db = FakeSession()
    db.rows["sessions"] = [_make_session(overrides_json={"min_length_seconds": -1})]
    job = _make_job(metadata_json={"pending_session_id": "ses_x"})
    result = await _resolve_min_length_override(db, job)  # type: ignore[arg-type]
    assert result is None


@pytest.mark.asyncio
async def test_zero_is_valid() -> None:
    """0 means "no minlength filter" — pass through to makemkvcon as-is."""
    db = FakeSession()
    db.rows["sessions"] = [_make_session(overrides_json={"min_length_seconds": 0})]
    job = _make_job(metadata_json={"pending_session_id": "ses_x"})
    result = await _resolve_min_length_override(db, job)  # type: ignore[arg-type]
    assert result == 0


@pytest.mark.asyncio
async def test_missing_session_returns_none() -> None:
    """If the pending_session_id doesn't resolve to a real Session
    (deleted between identify and rip-start), don't crash — just
    fall back to the baseline."""
    db = FakeSession()
    db.rows["sessions"] = []
    job = _make_job(metadata_json={"pending_session_id": "ses_gone"})
    result = await _resolve_min_length_override(db, job)  # type: ignore[arg-type]
    assert result is None
