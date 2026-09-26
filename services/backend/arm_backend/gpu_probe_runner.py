"""Backend-spawned per-device GPU encoder probe.

Each GPU row's usable encoders are verified by a real test encode: the
backend starts one short-lived transcode container per row, in
`python -m arm_transcode.main --probe-device` mode, with only that row's
device passed through. The worker prints one JSON line,
`{"verified": [<codec>...], "errors": {<encoder_id>: <str>}}`, and exits 0;
the runner writes `encoder_kinds = verified`, `probed_at = now` and a short
`probe_error` (None when anything verified) onto the row, then emits
`gpu.probed` on the `transcode.events` topic.

A non-zero exit or output without that JSON line (most often a transcode
image that predates `--probe-device`) is recorded as a probe failure telling
the operator to rebuild or pull the image, never as a silent "verified
nothing". Every probe writes `probed_at`, so a failed row shows its error
instead of looking unprobed; re-probing is an explicit operator action.

Mutual exclusion with the dispatcher's GPU claim: a row's id sits in
`dispatcher.probing_gpu_ids` for the whole probe (the claim skips those
rows), and a row that is BUSY with a transcode is never probed.

Triggers: `probe_unprobed` (a background pass started at boot, sequential,
enabled rows with no `probed_at` only) and `start_probe` (the re-probe
endpoints). Neither runs without a docker client.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError
from sqlmodel import col, select

from arm_backend.config import Settings, effective_transcode_capable
from arm_backend.transcode_dispatcher import TranscodeDispatcher
from arm_backend.transcode_images import image_for
from arm_backend.ws import WSHub
from arm_common import Gpu
from arm_common.enums import GpuStatus, GpuVendor

logger = logging.getLogger("arm_backend.gpu_probe_runner")

# Overall budget for one probe container: startup, test-clip generation, and
# one short test encode per catalog encoder of the vendor.
PROBE_TIMEOUT_S = 120
PROBE_COMMAND = ["python", "-m", "arm_transcode.main", "--probe-device"]
# Distinct from the dispatcher's task label so the transcode orphan sweeps
# never mistake a probe container for a task's transcoder.
PROBE_LABEL_KEY = "arm.gpu_probe"
STALE_IMAGE_ERROR = "probe failed (exit {code}); the transcode image may predate --probe-device: rebuild or pull it"
MAX_ERROR_CHARS = 500

ProbeOutcome = tuple[list[str], str | None]


def _truncate(text: str) -> str:
    return text[:MAX_ERROR_CHARS]


def _is_timeout(exc: BaseException) -> bool:
    """docker-py surfaces a `wait(timeout=...)` expiry as a requests
    ReadTimeout or a ConnectionError wrapping urllib3's read timeout,
    depending on the transport; match on the shape rather than one class."""
    if isinstance(exc, TimeoutError):
        return True
    return "timeout" in type(exc).__name__.lower() or "timed out" in str(exc).lower()


def parse_probe_output(status_code: int, stdout: bytes | str) -> ProbeOutcome:
    """Turn the probe container's exit code and stdout into
    `(verified codecs, probe_error)`.

    Only the LAST non-empty stdout line is parsed (the entrypoint may log
    before the worker runs). Anything other than exit 0 with a JSON object
    carrying a `verified` list is a failed probe.
    """
    text = stdout.decode("utf-8", "replace") if isinstance(stdout, bytes) else stdout
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    payload: Any = None
    if lines:
        try:
            payload = json.loads(lines[-1])
        except ValueError:
            payload = None
    if status_code != 0 or not isinstance(payload, dict) or not isinstance(payload.get("verified"), list):
        return [], STALE_IMAGE_ERROR.format(code=status_code)
    verified: list[str] = []
    for codec in payload["verified"]:
        if isinstance(codec, str) and codec not in verified:
            verified.append(codec)
    if verified:
        return verified, None
    errors = payload.get("errors")
    details = [f"{enc}: {msg}" for enc, msg in errors.items()] if isinstance(errors, dict) else []
    summary = "no encoder verified" + (": " + "; ".join(details) if details else "")
    return [], _truncate(summary)


class GpuProbeRunner:
    def __init__(
        self,
        settings: Settings,
        db_factory: async_sessionmaker[AsyncSession],
        dispatcher: TranscodeDispatcher,
        hub: WSHub,
    ) -> None:
        self._settings = settings
        self._db_factory = db_factory
        self._dispatcher = dispatcher
        self._hub = hub
        self._tasks: set[asyncio.Task[None]] = set()

    def capable(self) -> bool:
        """Whether probes can run at all: a transcode-capable deployment with
        a docker client (local socket or ARM_TRANSCODE_DOCKER_HOST)."""
        return effective_transcode_capable(self._settings) and self._dispatcher.docker_client is not None

    # --- triggers ----------------------------------------------------------

    def start_probe(self, gpu_id: str) -> bool:
        """Schedule a background probe of one row. Returns False when that row
        is already being probed. The row is reserved immediately, so a second
        request for it is refused even before the task starts."""
        probing = self._dispatcher.probing_gpu_ids
        if gpu_id in probing:
            return False
        probing.add(gpu_id)
        task = asyncio.create_task(self._probe_reserved(gpu_id))
        self._tasks.add(task)

        def _release(done: asyncio.Task[None]) -> None:
            # A done-callback rather than a `finally`: a task cancelled before
            # its first step never enters the coroutine at all.
            self._tasks.discard(done)
            probing.discard(gpu_id)

        task.add_done_callback(_release)
        return True

    def pending_tasks(self) -> list[asyncio.Task[None]]:
        return list(self._tasks)

    def cancel_pending(self) -> None:
        """Cancel every scheduled probe (backend shutdown). A container already
        running on the docker host is left to its own timeout."""
        for task in list(self._tasks):
            task.cancel()

    async def probe_unprobed(self) -> None:
        """Boot pass: probe every enabled row that has never been probed, one
        at a time. A no-op when probes can't run. Never raises."""
        if not self.capable():
            logger.info("gpu probe: boot pass skipped (no docker client for transcodes)")
            return
        try:
            async with self._db_factory() as db:
                rows = (await db.execute(select(Gpu).order_by(col(Gpu.vendor), col(Gpu.device_path)))).scalars().all()
                gpu_ids = [g.id for g in rows if g.enabled and g.probed_at is None]
        except Exception as exc:  # noqa: BLE001 - a boot-time background pass must never crash
            logger.exception("gpu probe: boot pass could not list GPUs: %s", exc)
            return
        if gpu_ids:
            logger.info("gpu probe: boot pass probing %d unprobed GPU(s)", len(gpu_ids))
        for gpu_id in gpu_ids:
            await self.probe_gpu(gpu_id)

    async def probe_gpu(self, gpu_id: str) -> None:
        """Probe one row now and write the result. Skips a row another probe
        already holds. Never raises."""
        probing = self._dispatcher.probing_gpu_ids
        if gpu_id in probing:
            logger.info("gpu probe: %s already being probed; skipping", gpu_id)
            return
        probing.add(gpu_id)
        try:
            await self._probe_reserved(gpu_id)
        finally:
            probing.discard(gpu_id)

    # --- one probe ---------------------------------------------------------

    async def _probe_reserved(self, gpu_id: str) -> None:
        """Probe a row whose id the caller already put in `probing_gpu_ids`."""
        try:
            async with self._db_factory() as db:
                gpu = (await db.execute(select(Gpu).where(col(Gpu.id) == gpu_id))).scalar_one_or_none()
            if gpu is None:
                logger.info("gpu probe: %s no longer exists; nothing to probe", gpu_id)
                return
            if gpu.claimed_by_task_id is not None or gpu.status == GpuStatus.BUSY:
                logger.info("gpu probe: %s is in use by a running transcode; not probing", gpu_id)
                return
            docker = self._dispatcher.docker_client
            if docker is None:
                logger.info("gpu probe: no docker client; not probing %s", gpu_id)
                return
            verified, error = await self._run_container(docker, gpu)
            await self._write(gpu_id, verified, error)
        except Exception as exc:  # noqa: BLE001 - a probe failure must never escape its task
            logger.exception("gpu probe: %s failed unexpectedly: %s", gpu_id, exc)

    def _run_kwargs(self, gpu: Gpu, image: str) -> dict[str, Any]:
        env = {
            "ARM_GPU_VENDOR": gpu.vendor.value,
            "ARM_GPU_DEVICE": gpu.device_path,
            "ARM_LOG_LEVEL": self._settings.ARM_LOG_LEVEL,
        }
        # Same uid/gid/render-group handling as a real transcode spawn, so the
        # probe runs under exactly the permissions the encode will.
        if self._settings.ARM_TRANSCODE_PUID:
            env["PUID"] = self._settings.ARM_TRANSCODE_PUID
        if self._settings.ARM_TRANSCODE_PGID:
            env["PGID"] = self._settings.ARM_TRANSCODE_PGID
        if gpu.vendor in (GpuVendor.VAAPI, GpuVendor.QSV) and self._settings.ARM_RENDER_GID:
            env["RENDER_GID"] = self._settings.ARM_RENDER_GID
        kwargs: dict[str, Any] = {
            "image": image,
            "command": list(PROBE_COMMAND),
            "labels": {PROBE_LABEL_KEY: gpu.id},
            "environment": env,
            # No /raw, /media or backend access: the probe encodes a generated
            # clip in its own scratch space and reports on stdout.
            "network": None,
            "detach": True,
            # Kept until `logs` is read after `wait`; removed in `finally`.
            "auto_remove": False,
        }
        self._dispatcher._inject_gpu_run_kwargs(kwargs, gpu)
        return kwargs

    async def _run_container(self, docker: Any, gpu: Gpu) -> ProbeOutcome:
        # image_exists may ping the docker host, so it runs off the loop too.
        image = await asyncio.to_thread(image_for, self._settings, gpu.vendor, exists=self._dispatcher.image_exists)
        kwargs = self._run_kwargs(gpu, image)
        logger.info("gpu probe: probing %s (%s %s) with %s", gpu.id, gpu.vendor.value, gpu.device_path, image)
        try:
            container = await asyncio.to_thread(lambda: docker.containers.run(**kwargs))
        except Exception as exc:  # noqa: BLE001 - reported on the row
            return [], _truncate(f"probe container could not start: {exc}")
        try:
            try:
                result = await asyncio.to_thread(container.wait, timeout=PROBE_TIMEOUT_S)
            except Exception as exc:  # noqa: BLE001 - reported on the row
                if _is_timeout(exc):
                    return [], f"probe timed out after {PROBE_TIMEOUT_S} s; the probe container was removed"
                return [], _truncate(f"probe failed while waiting for the container: {exc}")
            status_code = result.get("StatusCode", -1)
            stdout = await asyncio.to_thread(container.logs, stdout=True, stderr=False)
            return parse_probe_output(int(status_code), stdout)
        finally:
            try:
                await asyncio.to_thread(container.remove, force=True)
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup
                logger.warning("gpu probe: could not remove the probe container for %s: %s", gpu.id, exc)

    async def _write(self, gpu_id: str, verified: list[str], error: str | None) -> None:
        async with self._db_factory() as db:
            gpu = (await db.execute(select(Gpu).where(col(Gpu.id) == gpu_id))).scalar_one_or_none()
            if gpu is None:
                logger.info("gpu probe: %s was deleted while probing; result discarded", gpu_id)
                return
            # A row disabled mid-probe still records what it verified; the
            # eligibility rule already excludes disabled rows.
            gpu.encoder_kinds = verified
            gpu.probed_at = datetime.now(UTC)
            gpu.probe_error = error
            db.add(gpu)
            try:
                await db.commit()
            except StaleDataError:
                await db.rollback()
                logger.info("gpu probe: %s was deleted while probing; result discarded", gpu_id)
                return
            # After the commit, so a client refetching on the event sees the row.
            await self._hub.emit(
                topic="transcode.events", event_type="gpu.probed", payload={"gpu_id": gpu_id}, session=db
            )
            await db.commit()
        logger.info("gpu probe: %s verified %s%s", gpu_id, verified or "nothing", f" ({error})" if error else "")
