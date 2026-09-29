import pytest
from arm_common.enums import JobStatus
from arm_common.schemas.jobs import JobView, job_actions_for

# (can_resolve, can_apply, can_abandon, can_delete) per status. Written out in
# full so a membership change in enums.py shows up as a reviewed test diff.
EXPECTED = {
    JobStatus.CREATED: (False, False, True, False),
    JobStatus.AWAITING_USER_ID: (True, True, True, False),
    JobStatus.IDENTIFIED: (True, True, True, False),
    JobStatus.AWAITING_REVIEW: (True, False, True, False),
    JobStatus.RIPPING: (False, False, True, False),
    JobStatus.RIPPED: (True, True, False, True),
    JobStatus.RIPPED_PARTIAL: (True, True, False, True),
    JobStatus.RIPPED_AWAITING_IDENTIFY: (True, True, False, True),
    JobStatus.ABANDONED: (False, False, False, True),
    JobStatus.FAILED: (False, False, False, True),
}


def test_expected_covers_every_status() -> None:
    assert set(EXPECTED) == set(JobStatus)


@pytest.mark.parametrize("status", list(JobStatus))
def test_job_actions_for(status: JobStatus) -> None:
    a = job_actions_for(status)
    assert (a.can_resolve, a.can_apply, a.can_abandon, a.can_delete) == EXPECTED[status]


def test_job_view_serializes_actions() -> None:
    view = JobView(
        id="job_1",
        drive_id=None,
        disc_type="dvd",
        status=JobStatus.RIPPED,
        title="X",
        year=None,
        metadata_json={},
        resumed_from_crash=False,
    )
    dumped = view.model_dump(mode="json")
    assert dumped["actions"] == {"can_resolve": True, "can_apply": True, "can_abandon": False, "can_delete": True}
