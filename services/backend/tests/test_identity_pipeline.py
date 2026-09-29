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

from arm_backend.identity.pipeline import resolve_job, run_disc_hints, hint_title, hint_is_tv  # noqa: E402
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
    outcome = await resolve_job(db, job)  # type: ignore[arg-type]
    assert outcome.changed == 2
    assert outcome.track_ids == frozenset({"trk_1"})
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
    assert (await resolve_job(db, job)).changed == 2  # type: ignore[arg-type]
    assert (await resolve_job(db, job)).changed == 0  # type: ignore[arg-type]


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


def test_hint_is_tv_true_for_season_shaped_label() -> None:
    job = Job(id="job_1", drive_id="d", disc_type=DiscType.DVD, status=JobStatus.CREATED, metadata_json={})
    run_disc_hints(job, ScanResult(disc_type=DiscType.DVD, volume_label="LOST_S2D3"), now=NOW)
    assert hint_is_tv(job) is True


def test_hint_is_tv_false_for_movie_shaped_label() -> None:
    job = Job(id="job_1", drive_id="d", disc_type=DiscType.DVD, status=JobStatus.CREATED, metadata_json={})
    run_disc_hints(job, ScanResult(disc_type=DiscType.DVD, volume_label="LOTR_FELLOWSHIP_D2"), now=NOW)
    assert hint_is_tv(job) is False


def test_hint_is_tv_false_for_cd() -> None:
    job = Job(id="job_1", drive_id="d", disc_type=DiscType.CD, status=JobStatus.CREATED, metadata_json={})
    run_disc_hints(job, ScanResult(disc_type=DiscType.CD), now=NOW)
    assert hint_is_tv(job) is False


def test_run_disc_hints_handles_pathological_bd_name() -> None:
    # Pathological BD name (a disc-number digit run past int()'s digit-count
    # limit) no longer raises: parse_label's bounds check (finding 2, PR2
    # final review) catches the ValueError and drops the disc number, so
    # bd_title still runs to completion (status "ok", no disc claim).
    job = Job(id="job_1", drive_id="d", disc_type=DiscType.BLURAY, status=JobStatus.CREATED, metadata_json={})
    pathological_name = "X D" + "9" * 4301
    scan = ScanResult(disc_type=DiscType.BLURAY, volume_label="LOST_S2D3", bd_meta=BdDiscMeta(name=pathological_name))
    run_disc_hints(job, scan, now=NOW)
    sources = claims_of(job).sources
    assert sources["bd_title"].status == "ok"
    assert sources["bd_title"].job.model_dump(exclude_unset=True) == {"title": "x"}
    assert sources["label"].status == "ok"
    assert sources["label"].job.model_dump(exclude_unset=True) == {"season": 2, "disc_number": 3, "title": "lost"}
    # bd_title is ranked ahead of label and its (low-quality but non-empty)
    # title wins.
    assert hint_title(job) == "x"


def test_run_disc_hints_handles_source_applies_to_exception(monkeypatch) -> None:
    # When a source's applies_to method raises an exception, run_disc_hints
    # records status=error with the exception detail, and continues with other sources.
    from arm_backend.identity.sources import registry

    job = Job(id="job_1", drive_id="d", disc_type=DiscType.DVD, status=JobStatus.CREATED, metadata_json={})
    scan = ScanResult(disc_type=DiscType.DVD, volume_label="LOST_S2D3")

    # Monkeypatch BD_TITLE's applies_to to raise
    original_applies_to = registry.BD_TITLE.applies_to

    def boom(ctx):
        raise RuntimeError("intentional test error")

    monkeypatch.setattr(registry.BD_TITLE, "applies_to", boom)
    run_disc_hints(job, scan, now=NOW)
    monkeypatch.setattr(registry.BD_TITLE, "applies_to", original_applies_to)

    sources = claims_of(job).sources
    assert sources["bd_title"].status == "error"
    assert "RuntimeError" in sources["bd_title"].detail
    assert "intentional test error" in sources["bd_title"].detail
    # Label source should have run successfully
    assert sources["label"].status == "ok"
    assert sources["label"].job.model_dump(exclude_unset=True) == {"season": 2, "disc_number": 3, "title": "lost"}


def test_run_disc_hints_error_keeps_last_good_after_prior_ok(monkeypatch) -> None:
    """A source that previously matched on this job and now errors (e.g. a
    transient provider outage on re-run) must not wipe its earlier-good
    claims -- run_disc_hints stores through put_source's keep-last-good rule."""
    from arm_backend.identity.sources import registry

    job = Job(id="job_1", drive_id="d", disc_type=DiscType.BLURAY, status=JobStatus.CREATED, metadata_json={})
    scan = ScanResult(disc_type=DiscType.BLURAY, volume_label="LOST_S2D3", bd_meta=BdDiscMeta(name="The West Wing"))
    run_disc_hints(job, scan, now=NOW)
    assert claims_of(job).sources["bd_title"].status == "ok"

    def boom(ctx):
        raise RuntimeError("provider outage")

    monkeypatch.setattr(registry.BD_TITLE, "run", boom)
    run_disc_hints(job, scan, now=NOW)

    entry = claims_of(job).sources["bd_title"]
    assert entry.status == "ok"
    assert entry.job.model_dump(exclude_unset=True) == {"title": "the west wing"}
    assert entry.extra["last_error"]["detail"] == "RuntimeError: provider outage"
    assert hint_title(job) == "the west wing"


def test_run_disc_hints_handles_source_run_exception(monkeypatch) -> None:
    # When a source's run() method raises (applies_to said it applies), run_disc_hints
    # records status=error with the exception detail, and continues with other sources.
    from arm_backend.identity.sources import registry

    job = Job(id="job_1", drive_id="d", disc_type=DiscType.BLURAY, status=JobStatus.CREATED, metadata_json={})
    scan = ScanResult(
        disc_type=DiscType.BLURAY, volume_label="LOST_S2D3", bd_meta=BdDiscMeta(name="The West Wing Disc 2")
    )

    def boom(ctx):
        raise RuntimeError("intentional run() error")

    monkeypatch.setattr(registry.BD_TITLE, "run", boom)
    run_disc_hints(job, scan, now=NOW)

    sources = claims_of(job).sources
    assert sources["bd_title"].status == "error"
    assert "RuntimeError" in sources["bd_title"].detail
    assert "intentional run() error" in sources["bd_title"].detail
    # Label source should have run successfully
    assert sources["label"].status == "ok"
    assert sources["label"].job.model_dump(exclude_unset=True) == {"season": 2, "disc_number": 3, "title": "lost"}
