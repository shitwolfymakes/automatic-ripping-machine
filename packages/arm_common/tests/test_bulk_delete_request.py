from arm_common.schemas import BulkDeleteJobsRequest


def test_bulk_delete_request_defaults_to_no_filter() -> None:
    req = BulkDeleteJobsRequest()
    assert req.job_ids is None
    assert req.status is None


def test_bulk_delete_request_accepts_status_and_job_ids() -> None:
    req = BulkDeleteJobsRequest(status="failed", job_ids=["job_a", "job_b"])
    assert req.status == "failed"
    assert req.job_ids == ["job_a", "job_b"]
