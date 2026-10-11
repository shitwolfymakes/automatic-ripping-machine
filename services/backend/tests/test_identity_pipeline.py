"""resolve_job loads claims + tracks through the session and applies them."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_common import DiscType, Job, JobStatus, Track, TrackKind  # noqa: E402
from arm_common.enums import TrackRole  # noqa: E402
from arm_common.schemas.identity import SourceClaims, TrackClaim  # noqa: E402

from arm_backend.identity.pipeline import resolve_job  # noqa: E402
from arm_backend.identity.proposals import put_source  # noqa: E402
from tests._fakes import FakeSession  # noqa: E402


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
