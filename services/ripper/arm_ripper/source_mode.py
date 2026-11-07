"""The ripper's source mode: run the pipeline once against an ISO or folder source, then return so the container
exits."""

import asyncio
import logging

from arm_ripper import iso_extract
from arm_ripper.job_controller import JobController

logger = logging.getLogger("arm_ripper")


async def run_source_mode(controller: JobController, session_id: str | None) -> None:
    """One ISO, one pipeline run, then return so the container exits.

    Runs the pipeline through `handle_manual_trigger` (not `handle_disc_inserted`):
    the operator starting an ISO rip IS the explicit trigger, so it must not be
    gated by `auto_rip_on_insert` the way a disc-insert event would be.

    Cancellation (the job abandoned via `DELETE /api/iso/rips/{id}`, or the
    operator otherwise walking away) stays inside the task and we return
    normally so the container exits 0 — the backend's virtual-drive watchdog
    owns the drive-retire + container-removal cleanup either way. A
    CancelledError delivered to OUR OWN task (e.g. amain shutting down) is a
    different thing and must keep propagating, which is why we only swallow
    it when the inner task itself ended up cancelled.
    """
    task = asyncio.create_task(controller.handle_manual_trigger(session_id=session_id))
    try:
        await task
    except asyncio.CancelledError:
        if not task.cancelled():
            raise
        logger.info("source pipeline cancelled; exiting")
    finally:
        # The scratch copy of an image MakeMKV could only read once unpacked.
        await iso_extract.discard_all()
