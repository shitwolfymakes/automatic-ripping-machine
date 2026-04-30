"""Phase 9 — ripper-side crash recovery boot probe.

If the ripper container is restarting after a crash AND the backend says
there's still a RIPPING job assigned to this drive AND a disc is in the
tray, wipe `/raw/<job_id>/` and re-rip via the resume endpoint.

The disc-absent case (tray opened during crash) is logged and no-op'd —
the orphaned RIPPING row stays visible in the UI with the
`resumed_from_crash` badge, awaiting manual user intervention.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import httpx

from arm_ripper.backend_client import BackendClient
from arm_ripper.drive_poll import DriveState, read_drive_status
from arm_ripper.job_controller import JobController

logger = logging.getLogger("arm_ripper.recovery")

RAW_ROOT = Path("/raw")


def wipe_raw_dir(job_id: str) -> None:
    """Remove /raw/<job_id>/ and its contents. No-op if the directory
    does not exist. Safe to call repeatedly.
    """
    target = RAW_ROOT / job_id
    shutil.rmtree(target, ignore_errors=True)
    logger.info("wiped raw dir job_id=%s path=%s", job_id, target)


async def boot_probe(
    client: BackendClient,
    drive_id: str,
    device_path: str,
    controller: JobController,
) -> None:
    """Discover and resume any crashed in-flight job on this drive.

    Order:
    1. Query `/api/ripper/drives/{drive_id}/in-flight-job`.
    2. Probe `ioctl` for disc presence.
    3. Wipe `/raw/<job_id>/`.
    4. Hand off to `controller.resume_inflight_job`, which calls the
       backend `resume` endpoint and drives the rip-loop.

    All exceptions are logged and swallowed so the ripper boot continues
    to the normal `poll_loop` even on a misbehaving probe.
    """
    try:
        job = await client.get_in_flight_job(drive_id)
    except httpx.HTTPError as exc:
        logger.warning("boot probe: in-flight lookup failed: %s", exc)
        return

    if job is None:
        logger.debug("boot probe: no in-flight job for drive_id=%s", drive_id)
        return

    try:
        state = read_drive_status(device_path)
    except OSError as exc:
        logger.warning("boot probe: ioctl failed: %s", exc)
        return

    if state != DriveState.DISC_OK:
        logger.info(
            "boot probe: in-flight job_id=%s but drive state=%s; leaving as-is for manual recovery",
            job.id,
            state,
        )
        return

    logger.info("boot probe: resuming in-flight job_id=%s on drive_id=%s", job.id, drive_id)
    try:
        wipe_raw_dir(job.id)
        await controller.resume_inflight_job(job, device_path)
    except Exception as exc:  # noqa: BLE001 — boot must continue
        logger.exception("boot probe: resume failed for job_id=%s: %s", job.id, exc)
