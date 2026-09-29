from datetime import datetime, timezone

from arm_common import DiscType, Job, JobStatus
from arm_common.schemas import BdDiscMeta, ScanResult

from arm_backend.identity.sources.base import JobContext
from arm_backend.identity.sources.bd_title import BD_TITLE

NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)


def _ctx(meta: BdDiscMeta | None, disc_type: DiscType = DiscType.BLURAY) -> JobContext:
    job = Job(id="job_1", drive_id="d", disc_type=disc_type, status=JobStatus.CREATED, metadata_json={})
    return JobContext(job=job, scan=ScanResult(disc_type=disc_type, bd_meta=meta), now=NOW)


def test_set_position_overrides_parsed_disc() -> None:
    claims = BD_TITLE.run(_ctx(BdDiscMeta(name="The West Wing Season 3 Disc 5", set_number=2, num_sets=6)))
    assert claims.job.model_dump(exclude_unset=True) == {
        "season": 3,
        "disc_number": 2,
        "disc_total": 6,
        "title": "the west wing",
    }


def test_name_only() -> None:
    claims = BD_TITLE.run(_ctx(BdDiscMeta(name="Arrival")))
    assert claims.job.model_dump(exclude_unset=True) == {"title": "arrival"}
    assert claims.inputs == {"name": "Arrival"}


def test_skips_without_meta_or_on_dvd() -> None:
    assert BD_TITLE.applies_to(_ctx(None)) is not None
    assert BD_TITLE.applies_to(_ctx(BdDiscMeta(name="X"), DiscType.DVD)) is not None
    assert BD_TITLE.applies_to(_ctx(BdDiscMeta(name="X"))) is None
