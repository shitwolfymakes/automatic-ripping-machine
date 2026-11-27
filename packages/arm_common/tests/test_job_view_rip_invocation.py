"""`JobView.rip_invocation` reads the installed source when the view is built; mkv_all until one is installed."""

import pytest

from arm_common import DiscType, Job, JobStatus, RipInvocation
from arm_common.schemas import JobView
from arm_common.schemas import jobs as jobs_schema


def _job() -> Job:
    return Job(
        id="job_x",
        drive_id="drv_x",
        disc_type=DiscType.DVD,
        title="X",
        year=2000,
        status=JobStatus.RIPPED,
        metadata_json={},
        resumed_from_crash=False,
    )


def test_a_job_view_defaults_to_mkv_all_without_a_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs_schema, "_rip_invocation_source", jobs_schema._mkv_all)
    assert JobView.model_validate(_job()).rip_invocation is RipInvocation.MKV_ALL


def test_a_job_view_reads_the_installed_source_each_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs_schema, "_rip_invocation_source", jobs_schema._mkv_all)
    current = [RipInvocation.PER_TITLE]
    jobs_schema.set_rip_invocation_source(lambda: current[0])
    assert JobView.model_validate(_job()).rip_invocation is RipInvocation.PER_TITLE
    current[0] = RipInvocation.MKV_ALL
    assert JobView.model_validate(_job()).rip_invocation is RipInvocation.MKV_ALL
