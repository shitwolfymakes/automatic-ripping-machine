from arm_common import Job
from arm_common.enums import JobStatus
from arm_common.schemas.jobs import JobView


def test_job_model_has_disc_fields_defaulting_none():
    job = Job(drive_id="drv_1", disc_type="cd", status=JobStatus.CREATED, resumed_from_crash=False)
    assert job.disc_number is None
    assert job.disc_total is None


def test_job_round_trips_disc_fields():
    job = Job(
        drive_id="drv_1",
        disc_type="cd",
        disc_number=2,
        disc_total=3,
        status=JobStatus.CREATED,
        resumed_from_crash=False,
    )
    assert (job.disc_number, job.disc_total) == (2, 3)


def test_jobview_exposes_disc_fields():
    job = Job(
        drive_id="drv_1",
        disc_type="cd",
        disc_number=1,
        disc_total=2,
        status=JobStatus.CREATED,
        resumed_from_crash=False,
    )
    view = JobView.model_validate(job)
    assert view.disc_number == 1
    assert view.disc_total == 2
