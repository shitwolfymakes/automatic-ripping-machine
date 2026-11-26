"""How a resumed DVD/BD rip reads the disc again: one `mkv all`, or one invocation per unsettled title.

`mkv all` reads every title at or above the minimum length, settled and unselected ones included, and the resume
deletes the files of the settled ones. Ripping per title reads only what is left, at the cost of opening the disc once
per title. In `auto` the choice is by data: per title when the unsettled titles' expected bytes are at most
`per_title_max_remaining_pct` percent of what `mkv all` would read.
"""

import logging
from collections.abc import Collection
from dataclasses import dataclass

from arm_common import ResumeMode
from arm_common.schemas import ResumePolicy, TrackView

from arm_ripper.rip.optical_rip import _eligible_source_indexes, _index_tracks

logger = logging.getLogger("arm_ripper.job_controller")


@dataclass(frozen=True)
class ResumePlan:
    """The path a resume takes, why, and the figures the choice was made from.

    The byte figures are the scan's expected sizes; None when a title's size is unknown.
    """

    per_title: bool
    reason: str
    remaining_titles: int
    remaining_bytes: int | None
    mkv_all_bytes: int | None
    settled_bytes: int | None

    @property
    def remaining_pct(self) -> float | None:
        """The unsettled titles' share of what `mkv all` would read, in percent; None when it can't be worked out."""
        if self.remaining_bytes is None or not self.mkv_all_bytes:
            return None
        return 100.0 * self.remaining_bytes / self.mkv_all_bytes


def _sum_sizes(tracks: list[TrackView]) -> int | None:
    """The tracks' total expected size; None when any of them has no expected size."""
    sizes = [t.expected_size_bytes for t in tracks]
    return None if any(size is None for size in sizes) else sum(size for size in sizes if size is not None)


def plan_resume(
    tracks: list[TrackView],
    settled_ids: Collection[str],
    min_length_seconds: int,
    policy: ResumePolicy,
) -> ResumePlan:
    """Choose how a resume reads the disc, following `policy`."""
    track_by_index, _invalid = _index_tracks(tracks, settled_ids)
    eligible = [track_by_index[idx] for idx in _eligible_source_indexes(track_by_index, min_length_seconds)]
    remaining = [t for t in eligible if t.id not in settled_ids]
    remaining_bytes = _sum_sizes(remaining)
    mkv_all_bytes = _sum_sizes(eligible)
    settled_bytes = _sum_sizes([t for t in eligible if t.id in settled_ids])

    def plan(per_title: bool, reason: str) -> ResumePlan:
        return ResumePlan(
            per_title=per_title,
            reason=reason,
            remaining_titles=len(remaining),
            remaining_bytes=remaining_bytes,
            mkv_all_bytes=mkv_all_bytes,
            settled_bytes=settled_bytes,
        )

    if policy.mode is ResumeMode.MKV_ALL:
        return plan(False, "ARM_RESUME_MODE=mkv_all")
    if policy.mode is ResumeMode.PER_TITLE:
        return plan(True, "ARM_RESUME_MODE=per_title")
    if not remaining:
        return plan(True, "no unsettled title is left to read")
    pct = plan(False, "").remaining_pct
    if pct is None:
        return plan(False, "a title's expected size is unknown")
    limit = policy.per_title_max_remaining_pct
    if pct <= limit:
        return plan(True, f"{pct:.1f}% left <= {limit}%")
    return plan(False, f"{pct:.1f}% left > {limit}%")


def log_resume_plan(plan: ResumePlan, policy: ResumePolicy) -> None:
    """Log the choice as a `rip.resume_plan` event, with every input, so the defaults can be tuned from real resumes."""
    pct = plan.remaining_pct
    logger.info(
        "resume plan: %s (%s); %d title(s) left",
        "per title" if plan.per_title else "mkv all",
        plan.reason,
        plan.remaining_titles,
        extra={
            "event": "rip.resume_plan",
            "path": "per_title" if plan.per_title else "mkv_all",
            "reason": plan.reason,
            "mode": policy.mode.value,
            "per_title_max_remaining_pct": policy.per_title_max_remaining_pct,
            "remaining_titles": plan.remaining_titles,
            "remaining_bytes": plan.remaining_bytes,
            "mkv_all_bytes": plan.mkv_all_bytes,
            "settled_bytes": plan.settled_bytes,
            "remaining_pct": None if pct is None else round(pct, 1),
        },
    )
