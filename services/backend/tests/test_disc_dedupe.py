"""Tests for arm_backend.disc_dedupe.find_reusable_job_for_disc."""

import pytest
from arm_common.enums import JobStatus
from arm_common.models.disc_fingerprint import DiscFingerprint
from arm_common.models.job import Job
from arm_backend.disc_dedupe import ReuseDecision, find_reusable_job_for_disc

from tests._fakes import FakeSession


def _job(job_id: str, *, drive_id: str, status: JobStatus) -> Job:
    return Job(id=job_id, drive_id=drive_id, disc_type="dvd", status=status, metadata_json={})


def _fp(job_id: str, algo: str, value: str) -> DiscFingerprint:
    return DiscFingerprint(job_id=job_id, algo=algo, value=value)


@pytest.mark.asyncio
async def test_pre_rip_match_returns_reuse():
    db = FakeSession()
    db.rows["jobs"] = [_job("job_a", drive_id="drv_1", status=JobStatus.AWAITING_USER_ID)]
    db.rows["disc_fingerprints"] = [_fp("job_a", "crc64", "abc")]
    decision = await find_reusable_job_for_disc(db, drive_id="drv_1", fingerprints=[("crc64", "abc")])
    assert decision is not None
    assert decision.action == "reuse"
    assert decision.job.id == "job_a"


@pytest.mark.asyncio
async def test_ripping_match_returns_in_flight():
    db = FakeSession()
    db.rows["jobs"] = [_job("job_a", drive_id="drv_1", status=JobStatus.RIPPING)]
    db.rows["disc_fingerprints"] = [_fp("job_a", "crc64", "abc")]
    decision = await find_reusable_job_for_disc(db, drive_id="drv_1", fingerprints=[("crc64", "abc")])
    assert decision is not None
    assert decision.action == "in_flight"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "st",
    [
        JobStatus.RIPPED,
        JobStatus.RIPPED_PARTIAL,
        JobStatus.ABANDONED,
        JobStatus.FAILED,
        JobStatus.RIPPED_AWAITING_IDENTIFY,
    ],
)
async def test_terminal_match_returns_none(st):
    db = FakeSession()
    db.rows["jobs"] = [_job("job_a", drive_id="drv_1", status=st)]
    db.rows["disc_fingerprints"] = [_fp("job_a", "crc64", "abc")]
    decision = await find_reusable_job_for_disc(db, drive_id="drv_1", fingerprints=[("crc64", "abc")])
    assert decision is None


@pytest.mark.asyncio
async def test_no_fingerprint_match_returns_none():
    db = FakeSession()
    db.rows["jobs"] = [_job("job_a", drive_id="drv_1", status=JobStatus.AWAITING_USER_ID)]
    db.rows["disc_fingerprints"] = [_fp("job_a", "crc64", "abc")]
    decision = await find_reusable_job_for_disc(db, drive_id="drv_1", fingerprints=[("crc64", "different")])
    assert decision is None


@pytest.mark.asyncio
async def test_other_drive_match_returns_none():
    db = FakeSession()
    db.rows["jobs"] = [_job("job_a", drive_id="drv_OTHER", status=JobStatus.AWAITING_USER_ID)]
    db.rows["disc_fingerprints"] = [_fp("job_a", "crc64", "abc")]
    decision = await find_reusable_job_for_disc(db, drive_id="drv_1", fingerprints=[("crc64", "abc")])
    assert decision is None


@pytest.mark.asyncio
async def test_multi_algo_any_match():
    db = FakeSession()
    db.rows["jobs"] = [_job("job_a", drive_id="drv_1", status=JobStatus.IDENTIFIED)]
    db.rows["disc_fingerprints"] = [_fp("job_a", "crc64", "abc"), _fp("job_a", "aacs", "xyz")]
    decision = await find_reusable_job_for_disc(
        db, drive_id="drv_1", fingerprints=[("crc64", "nomatch"), ("aacs", "xyz")]
    )
    assert decision is not None and decision.action == "reuse"
