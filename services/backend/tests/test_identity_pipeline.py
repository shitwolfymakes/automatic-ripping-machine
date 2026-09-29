"""resolve_job loads claims + tracks through the session and applies them."""

import os
from datetime import datetime, timezone

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_common import DiscType, Job, JobStatus, Track, TrackKind  # noqa: E402
from arm_common.enums import TrackRole  # noqa: E402
from arm_common.schemas import BdDiscMeta, ScanResult  # noqa: E402
from arm_common.schemas.identity import SourceClaims, TrackClaim  # noqa: E402

from arm_backend.identity.pipeline import resolve_job, run_disc_hints, hint_title  # noqa: E402
from arm_backend.identity.proposals import put_source, claims_of  # noqa: E402
from tests._fakes import FakeSession  # noqa: E402

NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_resolve_job_applies_thediscdb_claims() -> None:
    db = FakeSession()
    job = Job(id="job_1", drive_id="d", disc_type=DiscType.BLURAY, status=JobStatus.IDENTIFIED, metadata_json={})
    track = Track(id="trk_1", job_id="job_1", kind=TrackKind.VIDEO_TITLE, index=1, source_ref="1")
    db.rows["jobs"] = [job]
    db.rows["tracks"] = [track]
    put_source(job, "thediscdb", SourceClaims(tracks={"1": TrackClaim(role=TrackRole.EPISODE, episode=3)}))
    changed = await resolve_job(db, job)  # type: ignore[arg-type]
    assert changed == 2
    assert track.episode_number == 3
    assert track.identity_provenance == {"role": "thediscdb", "episode_number": "thediscdb"}


@pytest.mark.asyncio
async def test_resolve_job_idempotent_second_call_changes_nothing() -> None:
    # Re-resolving an already-resolved job (e.g. ripper retry) must be a
    # no-op: same winners, nothing left to change.
    db = FakeSession()
    job = Job(id="job_2", drive_id="d", disc_type=DiscType.BLURAY, status=JobStatus.IDENTIFIED, metadata_json={})
    track = Track(id="trk_2", job_id="job_2", kind=TrackKind.VIDEO_TITLE, index=1, source_ref="1")
    db.rows["jobs"] = [job]
    db.rows["tracks"] = [track]
    put_source(job, "thediscdb", SourceClaims(tracks={"1": TrackClaim(role=TrackRole.EPISODE, episode=3)}))
    assert await resolve_job(db, job) == 2  # type: ignore[arg-type]
    assert await resolve_job(db, job) == 0  # type: ignore[arg-type]


def test_run_disc_hints_records_both_sources_and_skips() -> None:
    job = Job(id="job_1", drive_id="d", disc_type=DiscType.DVD, status=JobStatus.CREATED, metadata_json={})
    scan = ScanResult(disc_type=DiscType.DVD, volume_label="LOST_S2D3")
    run_disc_hints(job, scan, now=NOW)
    sources = claims_of(job).sources
    assert sources["bd_title"].status == "skipped"
    assert sources["label"].job.model_dump(exclude_unset=True) == {"season": 2, "disc_number": 3, "title": "lost"}
    assert hint_title(job) == "lost"


def test_hint_title_prefers_bd_title() -> None:
    job = Job(id="job_1", drive_id="d", disc_type=DiscType.BLURAY, status=JobStatus.CREATED, metadata_json={})
    scan = ScanResult(disc_type=DiscType.BLURAY, volume_label="WW_S3D2", bd_meta=BdDiscMeta(name="The West Wing"))
    run_disc_hints(job, scan, now=NOW)
    assert hint_title(job) == "the west wing"


def test_hint_title_none_without_hints() -> None:
    job = Job(id="job_1", drive_id="d", disc_type=DiscType.CD, status=JobStatus.CREATED, metadata_json={})
    run_disc_hints(job, ScanResult(disc_type=DiscType.CD), now=NOW)
    assert hint_title(job) is None


def test_run_disc_hints_handles_pathological_bd_name() -> None:
    # Pathological BD name (very long) causes parse_label to raise; bd_title
    # records error, label still works, hint_title uses label.
    job = Job(id="job_1", drive_id="d", disc_type=DiscType.BLURAY, status=JobStatus.CREATED, metadata_json={})
    pathological_name = "X D" + "9" * 4301
    scan = ScanResult(disc_type=DiscType.BLURAY, volume_label="LOST_S2D3", bd_meta=BdDiscMeta(name=pathological_name))
    run_disc_hints(job, scan, now=NOW)
    sources = claims_of(job).sources
    assert sources["bd_title"].status == "error"
    assert sources["bd_title"].detail  # non-empty detail
    assert sources["label"].status == "ok"
    assert sources["label"].job.model_dump(exclude_unset=True) == {"season": 2, "disc_number": 3, "title": "lost"}
    assert hint_title(job) == "lost"
