"""What an identity source is (design spec section 3.1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from arm_common import Job
from arm_common.schemas import ScanResult
from arm_common.schemas.identity import SourceClaims


class Capability(StrEnum):
    MANUAL = "manual"
    DISC_MAP = "disc_map"
    EPISODE_MATCH = "episode_match"
    DISC_HINT = "disc_hint"
    PRESET = "preset"


TIER_BY_CAPABILITY: dict[Capability, int] = {
    Capability.MANUAL: 1,
    Capability.DISC_MAP: 2,
    Capability.EPISODE_MATCH: 3,
    Capability.DISC_HINT: 4,
    Capability.PRESET: 5,
}


@dataclass(frozen=True)
class JobContext:
    job: Job
    scan: ScanResult
    now: datetime


class Source(Protocol):
    id: str
    capability: Capability

    def applies_to(self, ctx: JobContext) -> str | None:
        """None when the source should run; otherwise the reason it is skipped."""
        ...

    def run(self, ctx: JobContext) -> SourceClaims: ...
