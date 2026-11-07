import asyncio
import contextlib
import logging

from arm_ripper.drive_handle import DriveHandle
from arm_ripper.source import is_file_source

# The moved code keeps the job controller's logger name so existing log filters and log text stay the same.
logger = logging.getLogger("arm_ripper.job_controller")

# After makemkvcon exits, the kernel takes up to ~5s to release exclusive
# access on the optical drive — `eject` then sees EBUSY on open(). The
# delay schedule below is "best-effort with growing patience"; a healthy
# rip that holds the device briefly resolves on attempt 2.
EJECT_RETRY_DELAYS = (0.0, 2.0, 5.0, 10.0)
EJECT_PROCESS_TIMEOUT = 15.0


class Ejector:
    """Gets the disc out of the drive: best-effort umount, then eject with retries."""

    def __init__(self, device: DriveHandle) -> None:
        self._device = device

    async def eject(self, device_path: str) -> None:
        """Auto-eject with retries; non-fatal — logs but never raises.

        Two failure modes we have to tolerate:
        - EBUSY immediately post-rip while the kernel still holds the
          device for makemkvcon's close. Retries with growing delay clear
          this. (See EJECT_RETRY_DELAYS.)
        - The host (typical desktop with udisks2/gvfs) auto-mounted the
          disc behind our back. We cannot unmount the host's mount from
          inside the container, so the retries will all fail. Document
          host-side disable in [06-deployment.md].

        Best-effort `umount` first covers the case where a sibling
        container or the ripper's own scan-poster path mounted the
        device internally.
        """
        # The drive vanished (unplugged / powered off) between rip-complete
        # and here — there's no live node to umount/eject, and retrying just
        # produces a misleading "failed after N attempts" for a drive that
        # was never coming back. The poll loop's absence handling owns
        # recovery once it reattaches.
        if self._device.current is None:
            logger.info("eject skipped: drive is absent")
            return
        # ISO sources have no tray to eject. probe_disc reads the file
        # directly via PyCdlib and makemkvcon opens it read-only; nothing
        # mounts it, so there's nothing to umount or eject.
        if is_file_source(device_path):
            logger.info("eject skipped: source is ISO file %s", device_path)
            return
        await self._run_command("umount", device_path, log_failure=False)
        if not await self._try_eject(device_path):
            logger.error(
                "eject %s failed after %d attempts; check host auto-mount config",
                device_path,
                len(EJECT_RETRY_DELAYS),
            )

    async def _try_eject(self, device_path: str) -> bool:
        """Run eject once per EJECT_RETRY_DELAYS entry, waiting that long first, until one succeeds; True if one
        did."""
        for attempt, delay in enumerate(EJECT_RETRY_DELAYS, start=1):
            if delay > 0:
                await asyncio.sleep(delay)
            rc, stderr = await self._run_command("eject", "-sv", device_path)
            if rc == 0:
                logger.info("ejected %s on attempt %d", device_path, attempt)
                return True
            logger.warning(
                "eject %s attempt %d failed (rc=%s): %s",
                device_path,
                attempt,
                rc,
                stderr or "<no stderr>",
            )
        return False

    @staticmethod
    async def _run_command(*argv: str, log_failure: bool = True) -> tuple[int | None, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, OSError) as e:
            if log_failure:
                logger.warning("%s errored: %s", argv[0], e)
            return None, str(e)
        try:
            _, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=EJECT_PROCESS_TIMEOUT)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
            if log_failure:
                logger.warning("%s timed out", argv[0])
            return None, "timeout"
        return proc.returncode, stderr_b.decode(errors="replace").strip()
