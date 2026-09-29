from arm_common.enums import (
    JobStatus,
    TERMINAL_JOB_STATUSES,
    PRE_RIP_JOB_STATUSES,
    NON_TERMINAL_JOB_STATUSES,
    APPLY_OK_JOB_STATUSES,
    APPLY_PARK_JOB_STATUSES,
    POST_RIP_JOB_STATUSES,
    REDRAIN_JOB_STATUSES,
    RESOLVABLE_JOB_STATUSES,
    RESOLVABLE_PRESERVE_JOB_STATUSES,
    RESOLVABLE_PROMOTE_JOB_STATUSES,
)


def test_terminal_set_members():
    assert TERMINAL_JOB_STATUSES == frozenset(
        {
            JobStatus.RIPPED,
            JobStatus.RIPPED_PARTIAL,
            JobStatus.RIPPED_AWAITING_IDENTIFY,
            JobStatus.ABANDONED,
            JobStatus.FAILED,
        }
    )


def test_pre_rip_set_members():
    assert PRE_RIP_JOB_STATUSES == frozenset(
        {
            JobStatus.CREATED,
            JobStatus.AWAITING_USER_ID,
            JobStatus.IDENTIFIED,
            JobStatus.AWAITING_REVIEW,
        }
    )


def test_non_terminal_is_pre_rip_plus_ripping():
    assert NON_TERMINAL_JOB_STATUSES == PRE_RIP_JOB_STATUSES | {JobStatus.RIPPING}


def test_groups_partition_all_statuses():
    # every JobStatus is in exactly one of terminal / non-terminal
    assert TERMINAL_JOB_STATUSES | NON_TERMINAL_JOB_STATUSES == frozenset(JobStatus)
    assert TERMINAL_JOB_STATUSES & NON_TERMINAL_JOB_STATUSES == frozenset()


def test_resolvable_groups() -> None:
    assert RESOLVABLE_PROMOTE_JOB_STATUSES == {JobStatus.AWAITING_USER_ID, JobStatus.RIPPED_AWAITING_IDENTIFY}
    assert RESOLVABLE_PRESERVE_JOB_STATUSES == {
        JobStatus.IDENTIFIED,
        JobStatus.RIPPED,
        JobStatus.RIPPED_PARTIAL,
        JobStatus.AWAITING_REVIEW,
    }
    assert RESOLVABLE_JOB_STATUSES == RESOLVABLE_PROMOTE_JOB_STATUSES | RESOLVABLE_PRESERVE_JOB_STATUSES
    assert RESOLVABLE_PROMOTE_JOB_STATUSES & RESOLVABLE_PRESERVE_JOB_STATUSES == frozenset()


def test_apply_groups() -> None:
    assert APPLY_OK_JOB_STATUSES == {JobStatus.IDENTIFIED, JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL}
    assert APPLY_PARK_JOB_STATUSES == {JobStatus.AWAITING_USER_ID, JobStatus.RIPPED_AWAITING_IDENTIFY}
    assert APPLY_OK_JOB_STATUSES & APPLY_PARK_JOB_STATUSES == frozenset()


def test_post_rip_and_redrain_groups() -> None:
    assert POST_RIP_JOB_STATUSES == {JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL, JobStatus.RIPPED_AWAITING_IDENTIFY}
    assert REDRAIN_JOB_STATUSES == {JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL, JobStatus.IDENTIFIED}
