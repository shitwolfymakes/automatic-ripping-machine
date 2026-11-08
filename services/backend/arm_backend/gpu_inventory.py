"""Boot-time GPU inventory: seed the `gpus` table from ARM_GPUS when it is
empty, and free orphaned claims."""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.config import settings
from arm_backend.db import SessionLocal
from arm_backend.gpu_probe import load_configured_gpus
from arm_backend.ws import WSHub
from arm_common import Gpu, GpuStatus, TranscodeTask, TranscodeTaskStatus

logger = logging.getLogger(__name__)


async def _release_orphaned_gpu_claims(session: AsyncSession, gpus: Sequence[Gpu]) -> None:
    """Free BUSY rows no live task holds: the claim was nulled by a task
    delete (the FK only sets NULL), or its task already finished. A QUEUED
    or IN_PROGRESS claimant may be a transcoder that outlived the restart,
    so those stay for `sweep_stale_claims`."""
    released = 0
    for gpu in gpus:
        if gpu.status != GpuStatus.BUSY:
            continue
        task = None
        if gpu.claimed_by_task_id is not None:
            task = (
                await session.execute(select(TranscodeTask).where(col(TranscodeTask.id) == gpu.claimed_by_task_id))
            ).scalar_one_or_none()
        if task is not None and task.status in (TranscodeTaskStatus.QUEUED, TranscodeTaskStatus.IN_PROGRESS):
            continue
        gpu.status = GpuStatus.AVAILABLE
        gpu.claimed_by_task_id = None
        released += 1
    if released:
        logger.warning("gpu inventory: released %d orphaned GPU claim(s)", released)
        await session.commit()


async def refresh_gpu_inventory(hub: WSHub) -> None:
    """Seed the `gpus` table from `ARM_GPUS` - but only when it is empty.

    The table is DB-authoritative: operators manage devices from Settings >
    GPUs (enable/disable/delete), and those edits must survive restarts, so
    an already-populated table is left untouched. Deleting every row and
    restarting the backend is the deliberate re-seed path (the GPUs card
    documents it). The env descriptor comes from host-side detection at
    install time (or is hand-written for remote transcode hosts). Its
    `encoder_kinds` are hints only: seeded rows start with no verified
    encoders and `probed_at` NULL, and the boot probe pass
    (`GpuProbeRunner.probe_unprobed`) verifies each device. `load_configured_gpus`
    degrades to `[]` on malformed input. Emits `transcode.hw_unavailable` when
    the inventory ends up empty.
    """
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        existing = (await session.execute(select(Gpu))).scalars().all()
        if existing:
            logger.info("gpu inventory: %d device(s) in DB (authoritative); ARM_GPUS not consulted", len(existing))
            await _release_orphaned_gpu_claims(session, existing)
            return
        probed = load_configured_gpus(settings.ARM_GPUS)
        for g in probed:
            session.add(
                Gpu(
                    vendor=g.vendor,
                    device_path=g.device_path,
                    encoder_kinds=[],
                    status=GpuStatus.AVAILABLE,
                    last_seen_at=now,
                    probed_at=None,
                )
            )
        if probed:
            logger.info("gpu inventory: seeded %d device(s) from ARM_GPUS into an empty table", len(probed))
        else:
            await hub.emit(
                topic="transcode.events",
                event_type="transcode.hw_unavailable",
                payload={},
                session=session,
            )
        await session.commit()
