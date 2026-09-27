"""Backend-spawned per-device GPU encoder probe.

Each GPU row's usable encoders are verified by a real test encode: the
backend starts one short-lived transcode container per row, in
`python -m arm_transcode.main --probe-device` mode, with only that row's
device passed through. The worker prints one JSON line,
`{"verified": [<codec>...], "errors": {<encoder_id>: <str>}}`, and exits 0;
the runner writes `encoder_kinds = verified`, `probed_at = now` and a short
`probe_error` (None when anything verified) onto the row, then emits
`gpu.probed` on the `transcode.events` topic.

A failed probe is recorded with the worker's stderr tail, never as a silent
"verified nothing": exit 3 means the test clip could not be generated, exit 2
means the probe environment was rejected, and any other non-zero exit or
output without that JSON line (most often a transcode image that predates
`--probe-device`) tells the operator to rebuild or pull the image. Every
probe writes `probed_at`, so a failed row shows its error instead of looking
unprobed.

Mutual exclusion with the dispatcher's GPU claim: a row's id sits in
`dispatcher.probing_gpu_ids` for the whole probe (the claim skips those
rows), and a row that is BUSY with a transcode, or claimed by this process
but not yet committed (`dispatcher.claimed_gpu_ids`), is never probed.

Triggers: the boot pass (`start_boot_pass` -> `probe_unprobed`: removes
probe containers orphaned by a previous process, then probes, one at a time,
every enabled row that was never probed or has no verified encoder) and
`start_probe` (the re-probe endpoints and enabling a never-probed row).
Neither runs without a docker client.

While a never-probed row waits for its probe (reserved by the boot pass in
`dispatcher.pending_probe_gpu_ids`, or running in `probing_gpu_ids`), the
claim queues work that row could serve instead of falling back to the CPU
or failing (`TranscodeDispatcher.awaiting_probe`).
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
from arm_common.enums import GpuStatus, GpuVendor, VideoCodec

logger = logging.getLogger("arm_backend.gpu_probe_runner")

# Overall budget for one probe container: startup, test-clip generation, and
# one short test encode per catalog encoder of the vendor. Choosing the image
# can pull a missing per-vendor variant first; that pull happens before the
# container starts and is not counted against this timeout.
PROBE_TIMEOUT_S = 120
PROBE_COMMAND = ["python", "-m", "arm_transcode.main", "--probe-device"]
# Distinct from the dispatcher's task label so the transcode orphan sweeps
# never mistake a probe container for a task's transcoder.
PROBE_LABEL_KEY = "arm.gpu_probe"
STALE_IMAGE_ERROR = "probe failed (exit {code}); the transcode image may predate --probe-device: rebuild or pull it"
MAX_ERROR_CHARS = 500
# How long shutdown waits for cancelled probes to remove their containers.
SHUTDOWN_GRACE_S = 5.0
_STDERR_TAIL_LINES = 5
_KNOWN_CODECS = frozenset(c.value for c in VideoCodec)

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


def _decode(raw: bytes | str) -> str:
    return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw


def _stderr_tail(stderr: bytes | str) -> str:
    lines = [line.strip() for line in _decode(stderr).splitlines() if line.strip()]
    return " | ".join(lines[-_STDERR_TAIL_LINES:])


def parse_probe_payload(status_code: int, stdout: bytes | str) -> dict[str, Any] | None:
    """The worker's result object, or None when the probe did not succeed.

    Only the LAST non-empty stdout line is parsed (the entrypoint may log
    before the worker runs). Anything other than exit 0 with a JSON object
    carrying a `verified` list is a failed probe.
    """
    lines = [line.strip() for line in _decode(stdout).splitlines() if line.strip()]
    if status_code != 0 or not lines:
        return None
    try:
        payload = json.loads(lines[-1])
    except ValueError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("verified"), list):
        return None
    return payload


def probe_failure_error(status_code: int, stderr: bytes | str) -> str:
    """The row's `probe_error` for a probe that produced no result."""
    tail = _stderr_tail(stderr)
    if status_code == 3:
        message = "probe could not create its test clip" + (f": {tail}" if tail else "")
    elif status_code == 2:
        message = "probe misconfigured" + (f": {tail}" if tail else "")
    else:
        # An image that predates --probe-device exits 1: it starts as a
        # normal transcode worker and fails its config validation.
        message = STALE_IMAGE_ERROR.format(code=status_code) + (f"; stderr: {tail}" if tail else "")
    return _truncate(message)


def probe_outcome(payload: dict[str, Any]) -> ProbeOutcome:
    """`(verified codecs, probe_error)` from a successful probe's result.
    Codecs outside the catalog vocabulary are dropped and noted."""
    verified: list[str] = []
    unknown: list[str] = []
    for codec in payload["verified"]:
        if isinstance(codec, str) and codec in _KNOWN_CODECS:
            if codec not in verified:
                verified.append(codec)
        elif str(codec) not in unknown:
            unknown.append(str(codec))
    notes: list[str] = []
    if not verified:
        errors = payload.get("errors")
        details = [f"{enc}: {msg}" for enc, msg in errors.items()] if isinstance(errors, dict) else []
        notes.append("no encoder verified" + (": " + "; ".join(details) if details else ""))
    if unknown:
        notes.append("ignored unknown codec(s) from the probe: " + ", ".join(unknown))
    return verified, _truncate("; ".join(notes)) if notes else None


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

    def gpu_in_use(self, gpu: Gpu) -> bool:
        """BUSY with a transcode, or claimed by this process for a spawn whose
        claim is not yet committed (other sessions still read it AVAILABLE)."""
        return (
            gpu.claimed_by_task_id is not None
            or gpu.status == GpuStatus.BUSY
            or gpu.id in self._dispatcher.claimed_gpu_ids
        )

    def capable(self) -> bool:
        """Whether probes can run at all: a transcode-capable deployment with
        a docker client (local socket or ARM_TRANSCODE_DOCKER_HOST)."""
        return effective_transcode_capable(self._settings) and self._dispatcher.docker_client is not None

    # --- triggers ----------------------------------------------------------

    def start_probe(self, gpu_id: str) -> bool:
        """Schedule a background probe of one row. Returns False when that row
        is already being probed or holds an uncommitted claim. The row is
        reserved immediately, so a second request for it is refused even
        before the task starts."""
        probing = self._dispatcher.probing_gpu_ids
        if gpu_id in probing or gpu_id in self._dispatcher.claimed_gpu_ids:
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

    def start_boot_pass(self) -> asyncio.Task[None]:
        """Run `probe_unprobed` in the background; `shutdown` cancels it.

        When probes can run, `boot_probe_listing` is raised before this
        returns, so a dispatcher tick that runs before the pass has listed
        its rows already treats every never-probed row as awaiting a probe."""
        dispatcher = self._dispatcher
        if self.capable():
            dispatcher.boot_probe_listing = True
        task = asyncio.create_task(self.probe_unprobed())
        self._tasks.add(task)

        def _done(done: asyncio.Task[None]) -> None:
            # Also covers a task cancelled before its first step.
            self._tasks.discard(done)
            dispatcher.boot_probe_listing = False

        task.add_done_callback(_done)
        return task

    def pending_tasks(self) -> list[asyncio.Task[None]]:
        return list(self._tasks)

    async def shutdown(self, grace_s: float = SHUTDOWN_GRACE_S) -> None:
        """Cancel the boot pass and every scheduled probe, then wait briefly
        so each cancelled probe's `finally` removes its container (a probe
        container has no lifetime limit of its own beyond the runner's
        `wait`)."""
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=grace_s)

    async def remove_orphans(self) -> int:
        """Remove probe containers a previous backend process left behind
        (killed mid-probe). Containers of probes running now are kept. Never
        raises; returns how many were removed."""
        docker = self._dispatcher.docker_client
        if docker is None:
            return 0
        try:
            containers = await asyncio.to_thread(
                lambda: docker.containers.list(all=True, filters={"label": PROBE_LABEL_KEY})
            )
        except Exception as exc:  # noqa: BLE001 - cleanup is best-effort
            logger.warning("gpu probe: could not list orphaned probe containers: %s", exc)
            return 0
        removed = 0
        for container in containers:
            labels = getattr(container, "labels", None) or {}
            if labels.get(PROBE_LABEL_KEY) in self._dispatcher.probing_gpu_ids:
                continue
            try:
                await asyncio.to_thread(container.remove, force=True)
                removed += 1
            except Exception as exc:  # noqa: BLE001 - cleanup is best-effort
                logger.warning("gpu probe: could not remove orphaned probe container: %s", exc)
        if removed:
            logger.info("gpu probe: removed %d orphaned probe container(s)", removed)
        return removed

    async def probe_unprobed(self) -> None:
        """Boot pass: list the targets, remove orphaned probe containers, then
        probe, one at a time, every enabled row that was never probed or has
        no verified encoder (a failed or verified-nothing row is retried every
        boot). A no-op when probes can't run. Never raises.

        Every target id goes into `pending_probe_gpu_ids` in the same step
        that ends `boot_probe_listing` (no await in between), and leaves it
        when its own probe ends or the pass ends, however it ends."""
        dispatcher = self._dispatcher
        pending = dispatcher.pending_probe_gpu_ids
        reserved: list[str] = []
        try:
            if not self.capable():
                logger.info("gpu probe: boot pass skipped (no docker client for transcodes)")
                return
            try:
                async with self._db_factory() as db:
                    stmt = select(Gpu).order_by(col(Gpu.vendor), col(Gpu.device_path))
                    rows = (await db.execute(stmt)).scalars().all()
                    gpu_ids = [g.id for g in rows if g.enabled and (g.probed_at is None or not g.encoder_kinds)]
            except Exception as exc:  # noqa: BLE001 - a boot-time background pass must never crash
                logger.exception("gpu probe: boot pass could not list GPUs: %s", exc)
                return
            reserved = gpu_ids
            pending.update(reserved)
            dispatcher.boot_probe_listing = False
            await self.remove_orphans()
            if gpu_ids:
                logger.info("gpu probe: boot pass probing %d unprobed or unverified GPU(s)", len(gpu_ids))
            for gpu_id in gpu_ids:
                try:
                    await self.probe_gpu(gpu_id)
                finally:
                    pending.discard(gpu_id)
        finally:
            dispatcher.boot_probe_listing = False
            pending.difference_update(reserved)

    async def probe_gpu(self, gpu_id: str) -> None:
        """Probe one row now and write the result. Skips a row another probe
        already holds or one with an uncommitted claim. Never raises."""
        probing = self._dispatcher.probing_gpu_ids
        if gpu_id in probing:
            logger.info("gpu probe: %s already being probed; skipping", gpu_id)
            return
        if gpu_id in self._dispatcher.claimed_gpu_ids:
            logger.info("gpu probe: %s is being claimed by a transcode; skipping", gpu_id)
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
            if self.gpu_in_use(gpu):
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
        # variant_available may ping the docker host or pull a variant image,
        # so it runs off the loop too.
        image = await asyncio.to_thread(
            image_for, self._settings, gpu.vendor, exists=self._dispatcher.variant_available
        )
        kwargs = self._run_kwargs(gpu, image)
        logger.info("gpu probe: probing %s (%s %s) with %s", gpu.id, gpu.vendor.value, gpu.device_path, image)
        try:
            container = await asyncio.to_thread(lambda: docker.containers.run(**kwargs))
        except Exception as exc:  # noqa: BLE001 - reported on the row
            # `run` creates the container before starting it, so a start
            # failure leaves a Created container behind with no handle to it.
            await self._remove_probe_containers(docker, gpu.id)
            return [], _truncate(f"probe container could not start: {exc}")
        try:
            try:
                result = await asyncio.to_thread(container.wait, timeout=PROBE_TIMEOUT_S)
            except Exception as exc:  # noqa: BLE001 - reported on the row
                if _is_timeout(exc):
                    return [], f"probe timed out after {PROBE_TIMEOUT_S} s; the probe container was removed"
                return [], _truncate(f"probe failed while waiting for the container: {exc}")
            raw_code = result.get("StatusCode")
            status_code = raw_code if isinstance(raw_code, int) else -1
            stdout = await asyncio.to_thread(container.logs, stdout=True, stderr=False)
            payload = parse_probe_payload(status_code, stdout)
            if payload is not None:
                return probe_outcome(payload)
            stderr = await asyncio.to_thread(container.logs, stdout=False, stderr=True)
            return [], probe_failure_error(status_code, stderr)
        finally:
            try:
                await asyncio.to_thread(container.remove, force=True)
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup
                logger.warning("gpu probe: could not remove the probe container for %s: %s", gpu.id, exc)

    async def _remove_probe_containers(self, docker: Any, gpu_id: str) -> None:
        """Remove every container labelled as this row's probe. Only called
        while this probe holds the row's reservation. Never raises; one
        container failing to go does not stop the rest."""
        try:
            containers = await asyncio.to_thread(
                lambda: docker.containers.list(all=True, filters={"label": f"{PROBE_LABEL_KEY}={gpu_id}"})
            )
        except Exception as exc:  # noqa: BLE001 - best-effort cleanup
            logger.warning("gpu probe: could not list the unstarted probe containers for %s: %s", gpu_id, exc)
            return
        for container in containers:
            try:
                await asyncio.to_thread(container.remove, force=True)
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup
                logger.warning("gpu probe: could not remove the unstarted probe container for %s: %s", gpu_id, exc)

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
