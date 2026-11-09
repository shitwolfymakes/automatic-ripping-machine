"""Topic naming rules shared by the WS router and hub: which topics are
progress streams, and the ids a progress topic carries."""

from __future__ import annotations

from typing import Any


def is_progress_topic(topic: str) -> bool:
    """Whether the topic is a ripper or transcode progress stream, which is
    never persisted."""
    return topic.startswith("ripper.progress.") or topic.startswith("transcode.progress.")


def progress_scope(topic: str, payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """The job id a published topic carries, and its throttle scope: the
    payload's track id, else the transcode task id."""
    job_id = _extract_id(topic, "ripper.progress.")
    # transcode.progress.{task_id} → use the task_id as the throttle scope (same role as track_id).
    track_id: str | None = None
    if isinstance(payload, dict):  # pragma: no branch — WSPublishRequest.payload is schema-constrained to dict
        track_id = payload.get("track_id")
    if track_id is None:
        track_id = _extract_id(topic, "transcode.progress.")
    return job_id, track_id


def _extract_id(topic: str, prefix: str) -> str | None:
    if topic.startswith(prefix):
        return topic[len(prefix) :] or None
    return None
