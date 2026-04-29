"""Per-principal topic authorization.

Each topic is parsed into `(prefix, scope_id)` and matched against the
principal's allowed surface. Unknown topics are rejected (fail-closed
per 05-cross-cutting.md § WebSocket security).
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.ws.principal import Principal, ServicePrincipal
from arm_common import Drive, Job


def _split(topic: str) -> tuple[str, str | None]:
    """`ripper.progress.job_abc` → ("ripper.progress", "job_abc"). Bare topics → (topic, None)."""
    if not topic:
        return ("", None)
    head, _, tail = topic.rpartition(".")
    # Untyped bare topics like "ripper.events" have no scope id — split returns ("ripper", "events")
    # which we don't want; detect by checking whether the suffix is a known scope-bearing token.
    if topic in {"ripper.events", "transcode.events", "system.events"}:
        return (topic, None)
    if head:
        return (head, tail)
    return (topic, None)


_UI_TOPIC_PREFIXES_NO_SCOPE: frozenset[str] = frozenset({"ripper.events", "transcode.events", "system.events"})
_UI_TOPIC_PREFIXES_WITH_SCOPE: frozenset[str] = frozenset({"ripper.progress", "transcode.progress", "logs"})


async def can_subscribe(principal: Principal, topic: str, session: AsyncSession) -> bool:
    prefix, scope = _split(topic)

    if isinstance(principal, ServicePrincipal):
        if principal.kind == "ripper":
            if prefix != "ripper.commands" or not scope:
                return False
            drive = (await session.execute(select(Drive).where(col(Drive.id) == scope))).scalar_one_or_none()
            return drive is not None and drive.hostname == principal.hostname
        # transcoder
        return prefix == "transcoder.commands" and scope is not None and scope == principal.task_id

    # UIPrincipal
    if topic in _UI_TOPIC_PREFIXES_NO_SCOPE:
        return True
    return prefix in _UI_TOPIC_PREFIXES_WITH_SCOPE and scope is not None


async def can_publish(principal: Principal, topic: str, session: AsyncSession) -> bool:
    prefix, scope = _split(topic)

    if isinstance(principal, ServicePrincipal):
        if principal.kind != "ripper":
            return False
        if prefix != "ripper.progress" or not scope:
            return False
        job = (await session.execute(select(Job).where(col(Job.id) == scope))).scalar_one_or_none()
        if job is None:
            return False
        drive = (await session.execute(select(Drive).where(col(Drive.id) == job.drive_id))).scalar_one_or_none()
        return drive is not None and drive.hostname == principal.hostname

    # UI never publishes; backend uses hub.emit() in-process.
    return False
