"""Encoder catalog availability — GET /api/encoders.

`arm_common.encoders.ENCODERS` is a static catalog: it has no idea which
devices this deployment actually has. This router layers the live `gpus`
inventory on top of it (the same `gpu_is_eligible` rule the transcode
dispatcher's GPU claim uses) so the transcode preset picker can grey out, or
explain, an encoder the deployment can't currently satisfy — without
duplicating that eligibility rule client-side.
"""

from collections.abc import Sequence
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_common import Gpu, User
from arm_common.encoders import ENCODERS, EncoderSpec, gpu_is_eligible
from arm_common.enums import GpuVendor
from arm_common.schemas import EncoderAvailabilityView

router = APIRouter(prefix="/api/encoders", tags=["encoders"])

_GPU_GROUPS: dict[GpuVendor, Literal["qsv", "nvenc", "vaapi"]] = {
    GpuVendor.QSV: "qsv",
    GpuVendor.NVENC: "nvenc",
    GpuVendor.VAAPI: "vaapi",
}


def _availability(spec: EncoderSpec, gpus: Sequence[Gpu]) -> EncoderAvailabilityView:
    kind = spec.kind
    reason: str | None = None
    if kind == "gpu":
        assert spec.vendor is not None  # every catalog "gpu" spec sets vendor (arm_common.encoders._build)
        group: Literal["preset", "cpu", "any", "qsv", "nvenc", "vaapi"] = _GPU_GROUPS[spec.vendor]
        codec = str(spec.codec)
        available = any(gpu_is_eligible(g, codec) and g.vendor == spec.vendor for g in gpus)
        if not available:
            reason = f"no enabled device has verified {spec.id}"
    elif kind == "any":
        group = kind
        codec = str(spec.codec)
        available = True
        if not any(gpu_is_eligible(g, codec) for g in gpus):
            reason = "no verified GPU; runs on the CPU"
    else:
        group = kind
        available = True

    return EncoderAvailabilityView(
        id=spec.id,
        label=spec.label,
        group=group,
        engine=spec.engine,
        kind=spec.kind,
        vendor=spec.vendor,
        codec=spec.codec,
        available=available,
        reason=reason,
    )


@router.get("", response_model=list[EncoderAvailabilityView])
async def list_encoders(
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> list[EncoderAvailabilityView]:
    all_gpus = (await db.execute(select(Gpu))).scalars().all()
    return [_availability(spec, all_gpus) for spec in ENCODERS.values()]
