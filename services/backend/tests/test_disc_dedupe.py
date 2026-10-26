"""Tests for arm_backend.disc_dedupe: find_reusable_job_for_disc and find_previous_rips."""

from datetime import UTC, datetime

import pytest
from arm_common.enums import JobStatus
from arm_common.models.disc_fingerprint import DiscFingerprint
from arm_common.models.job import Job
from arm_backend.disc_dedupe import find_previous_rips, find_reusable_job_for_disc

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


@pytest.mark.asyncio
async def test_blank_algo_or_value_fingerprints_short_circuit() -> None:
    """Entries with an empty algo or value are discarded before any query; if
    nothing usable remains the lookup returns None without touching the DB."""
    db = FakeSession()
    db.rows["jobs"] = [_job("job_a", drive_id="drv_1", status=JobStatus.RIPPING)]
    db.rows["disc_fingerprints"] = [_fp("job_a", "crc64", "abc")]
    decision = await find_reusable_job_for_disc(db, drive_id="drv_1", fingerprints=[("", "abc"), ("crc64", "")])
    assert decision is None


# --- find_previous_rips (D-132) --------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("st", [JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL, JobStatus.RIPPED_AWAITING_IDENTIFY])
async def test_previous_rip_matches_a_ripped_job_on_any_drive(st):
    db = FakeSession()
    db.rows["jobs"] = [_job("job_a", drive_id="drv_OTHER", status=st)]
    db.rows["disc_fingerprints"] = [_fp("job_a", "matrix256", "79ee")]
    assert [j.id for j in await find_previous_rips(db, fingerprints=[("matrix256", "79ee")])] == ["job_a"]


@pytest.mark.asyncio
@pytest.mark.parametrize("st", [JobStatus.FAILED, JobStatus.ABANDONED, JobStatus.RIPPING, JobStatus.AWAITING_REVIEW])
async def test_previous_rip_ignores_jobs_that_did_not_rip(st):
    db = FakeSession()
    db.rows["jobs"] = [_job("job_a", drive_id="drv_1", status=st)]
    db.rows["disc_fingerprints"] = [_fp("job_a", "matrix256", "79ee")]
    assert await find_previous_rips(db, fingerprints=[("matrix256", "79ee")]) == []


@pytest.mark.asyncio
async def test_previous_rip_needs_the_same_algo_and_value():
    db = FakeSession()
    db.rows["jobs"] = [_job("job_a", drive_id="drv_1", status=JobStatus.RIPPED)]
    db.rows["disc_fingerprints"] = [_fp("job_a", "crc64", "79ee")]
    assert await find_previous_rips(db, fingerprints=[("matrix256", "79ee")]) == []
    assert await find_previous_rips(db, fingerprints=[("", ""), ("crc64", "")]) == []


@pytest.mark.asyncio
async def test_previous_rips_lists_every_match_newest_first():
    db = FakeSession()
    db.rows["jobs"] = [
        _job("job_01A", drive_id="drv_1", status=JobStatus.RIPPED),
        _job("job_01C", drive_id="drv_2", status=JobStatus.RIPPED_PARTIAL),
        _job("job_01B", drive_id="drv_1", status=JobStatus.RIPPED),
    ]
    db.rows["disc_fingerprints"] = [
        _fp("job_01A", "matrix256", "79ee"),
        _fp("job_01B", "matrix256", "79ee"),
        _fp("job_01C", "thediscdb", "beef"),
    ]
    previous = await find_previous_rips(db, fingerprints=[("matrix256", "79ee"), ("thediscdb", "beef")])
    assert [j.id for j in previous] == ["job_01C", "job_01B", "job_01A"]


@pytest.mark.asyncio
async def test_same_source_reuses_the_newest_parked_job_without_fingerprints():
    # A virtual drive (ISO or disc folder) has one source for life: a ripper
    # started again for its parked rip must land in that job, and ISO scans
    # carry no fingerprints to match on.
    db = FakeSession()
    older = _job("job_old", drive_id="drv_iso", status=JobStatus.AWAITING_REVIEW)
    newer = _job("job_new", drive_id="drv_iso", status=JobStatus.AWAITING_REVIEW)
    older.created_at = datetime(2026, 10, 24, tzinfo=UTC)
    newer.created_at = datetime(2026, 10, 25, tzinfo=UTC)
    db.rows["jobs"] = [older, newer, _job("job_other", drive_id="drv_1", status=JobStatus.AWAITING_REVIEW)]
    decision = await find_reusable_job_for_disc(db, drive_id="drv_iso", fingerprints=[], same_source=True)
    assert decision is not None and decision.action == "reuse" and decision.job.id == "job_new"


@pytest.mark.asyncio
async def test_same_source_in_flight_while_ripping_and_none_without_a_job():
    db = FakeSession()
    db.rows["jobs"] = [_job("job_a", drive_id="drv_iso", status=JobStatus.RIPPING)]
    decision = await find_reusable_job_for_disc(db, drive_id="drv_iso", fingerprints=[], same_source=True)
    assert decision is not None and decision.action == "in_flight"
    assert await find_reusable_job_for_disc(db, drive_id="drv_none", fingerprints=[], same_source=True) is None


@pytest.mark.asyncio
async def test_same_source_still_matches_fingerprints_when_the_scan_has_them():
    db = FakeSession()
    db.rows["jobs"] = [_job("job_a", drive_id="drv_iso", status=JobStatus.AWAITING_USER_ID)]
    db.rows["disc_fingerprints"] = [_fp("job_a", "crc64", "abc")]
    hit = await find_reusable_job_for_disc(db, drive_id="drv_iso", fingerprints=[("crc64", "abc")], same_source=True)
    miss = await find_reusable_job_for_disc(db, drive_id="drv_iso", fingerprints=[("crc64", "zzz")], same_source=True)
    assert hit is not None and hit.job.id == "job_a"
    assert miss is None  # a fingerprint that does not match is a different disc
