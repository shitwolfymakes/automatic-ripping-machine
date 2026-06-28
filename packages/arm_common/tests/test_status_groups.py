from arm_common.enums import (
    JobStatus,
    TERMINAL_JOB_STATUSES,
    PRE_RIP_JOB_STATUSES,
    NON_TERMINAL_JOB_STATUSES,
)


def test_terminal_set_members():
    assert TERMINAL_JOB_STATUSES == frozenset({
        JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL, JobStatus.RIPPED_AWAITING_IDENTIFY,
        JobStatus.ABANDONED, JobStatus.FAILED,
    })


def test_pre_rip_set_members():
    assert PRE_RIP_JOB_STATUSES == frozenset({
        JobStatus.CREATED, JobStatus.AWAITING_USER_ID, JobStatus.IDENTIFIED,
        JobStatus.AWAITING_REVIEW,
    })


def test_non_terminal_is_pre_rip_plus_ripping():
    assert NON_TERMINAL_JOB_STATUSES == PRE_RIP_JOB_STATUSES | {JobStatus.RIPPING}


def test_groups_partition_all_statuses():
    # every JobStatus is in exactly one of terminal / non-terminal
    assert TERMINAL_JOB_STATUSES | NON_TERMINAL_JOB_STATUSES == frozenset(JobStatus)
    assert TERMINAL_JOB_STATUSES & NON_TERMINAL_JOB_STATUSES == frozenset()
