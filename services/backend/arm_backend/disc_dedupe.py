"""Find an existing job to reuse for a re-scanned disc, so a ripper restart /
re-identify on a disc-in-drive does not mint a duplicate Job.

Caller (identify) supplies the scan's (algo, value) fingerprints. We look up the
drive's non-terminal jobs and match by any shared fingerprint:
  - pre-rip status  -> reuse  (refresh scan, preserve identity + pending_session_id)
  - ripping         -> in_flight (restart-race; return the live job)
  - no match        -> None  (caller creates a fresh Job)

FakeSession can't evaluate a multi-table JOIN, so we fetch candidate jobs by
drive+status, then match fingerprints in Python — mirroring drives.py:_current_job.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Literal, NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_common.enums import NON_TERMINAL_JOB_STATUSES, PRE_RIP_JOB_STATUSES
from arm_common.models.disc_fingerprint import DiscFingerprint
from arm_common.models.job import Job

logger = logging.getLogger("arm_backend")


class ReuseDecision(NamedTuple):
    job: Job
    action: Literal["reuse", "in_flight"]


async def find_reusable_job_for_disc(
    session: AsyncSession,
    *,
    drive_id: str,
    fingerprints: Sequence[tuple[str, str]],
) -> ReuseDecision | None:
    """Return a ReuseDecision if a non-terminal job on the same drive shares
    any (algo, value) fingerprint with the caller's scan; else None.

    Steps (single-table queries + Python matching, FakeSession-compatible):
      1. Fetch all non-terminal jobs for the given drive_id.
      2. Fetch all DiscFingerprint rows whose job_id is among those candidates.
      3. Match (algo, value) in Python; return on first hit.
    """
    if not fingerprints:
        return None
    wanted = {(a, v) for a, v in fingerprints if a and v}
    if not wanted:
        return None

    # Step 1: candidate jobs — drive_id match + non-terminal status.
    candidates: Sequence[Job] = (
        (
            await session.execute(
                select(Job)
                .where(col(Job.drive_id) == drive_id)
                .where(col(Job.status).in_(tuple(NON_TERMINAL_JOB_STATUSES)))
            )
        )
        .scalars()
        .all()
    )
    if not candidates:
        return None
    by_id = {j.id: j for j in candidates}

    # Step 2: fingerprints for those jobs.
    fps: Sequence[DiscFingerprint] = (
        (await session.execute(select(DiscFingerprint).where(col(DiscFingerprint.job_id).in_(tuple(by_id.keys())))))
        .scalars()
        .all()
    )

    # Step 3: Python match — first fingerprint hit wins.
    matched_job: Job | None = None
    for fp in fps:
        if (fp.algo, fp.value) in wanted:
            matched_job = by_id[fp.job_id]
            break

    if matched_job is None:
        return None

    action: Literal["reuse", "in_flight"] = "reuse" if matched_job.status in PRE_RIP_JOB_STATUSES else "in_flight"
    return ReuseDecision(job=matched_job, action=action)
