"""Per-principal topic authorization.

Each topic is parsed into `(prefix, scope_id)` and matched against the
principal's allowed surface. Unknown topics are rejected (fail-closed
per 05-cross-cutting.md § WebSocket security).
"""

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.ws.principal import Principal, PrincipalKind, ServicePrincipal
from arm_common import Drive, Job, TranscodeTask, TranscodeTaskStatus


# Bare topics: no scope id follows the prefix.
_UNSCOPED_TOPICS: frozenset[str] = frozenset({"ripper.events", "transcode.events", "system.events"})


def _split(topic: str) -> tuple[str, str | None]:
    """`ripper.progress.job_abc` → ("ripper.progress", "job_abc"). Bare topics → (topic, None)."""
    if not topic:
        return ("", None)
    head, _, tail = topic.rpartition(".")
    # Untyped bare topics like "ripper.events" have no scope id — split returns ("ripper", "events")
    # which we don't want; detect by checking whether the suffix is a known scope-bearing token.
    if topic in _UNSCOPED_TOPICS:
        return (topic, None)
    if head:
        return (head, tail)
    return (topic, None)


_UI_TOPIC_PREFIXES_WITH_SCOPE: frozenset[str] = frozenset({"ripper.progress", "transcode.progress", "logs"})


type _ServiceRule = Callable[[ServicePrincipal, str, str | None, AsyncSession], Awaitable[bool]]


async def _ripper_may_subscribe(
    principal: ServicePrincipal, prefix: str, scope: str | None, session: AsyncSession
) -> bool:
    """A ripper may subscribe only to its own drive's command topic."""
    if prefix != "ripper.commands" or not scope:
        return False
    drive = (await session.execute(select(Drive).where(col(Drive.id) == scope))).scalar_one_or_none()
    return drive is not None and drive.hostname == principal.hostname


async def _transcoder_may_subscribe(
    principal: ServicePrincipal, prefix: str, scope: str | None, session: AsyncSession
) -> bool:
    """A transcoder may subscribe only to its own task's command topic:
    while the task is queued (before the claim), then only as the claiming
    host.
    """
    if prefix != "transcoder.commands" or not scope or scope != principal.task_id:
        return False
    task = (await session.execute(select(TranscodeTask).where(col(TranscodeTask.id) == scope))).scalar_one_or_none()
    if task is None:
        return False
    # The transcoder subscribes before it POSTs /claim (so a cancel issued
    # right after the claim is not missed), so a QUEUED task is allowed
    # pre-claim. Once claimed, only the claiming host may subscribe,
    # mirroring can_publish.
    if task.status == TranscodeTaskStatus.QUEUED:
        return True
    return task.status == TranscodeTaskStatus.IN_PROGRESS and task.claimed_by == principal.hostname


def _ui_may_subscribe(topic: str, prefix: str, scope: str | None) -> bool:
    """The UI may subscribe to the bare event topics and to any scoped
    progress or log topic.
    """
    if topic in _UNSCOPED_TOPICS:
        return True
    return prefix in _UI_TOPIC_PREFIXES_WITH_SCOPE and scope is not None


_SUBSCRIBE_RULES: dict[PrincipalKind, _ServiceRule] = {
    "ripper": _ripper_may_subscribe,
    "transcoder": _transcoder_may_subscribe,
}


async def _ripper_may_publish(
    principal: ServicePrincipal, prefix: str, scope: str | None, session: AsyncSession
) -> bool:
    """A ripper may publish progress only for a job on its own drive."""
    if prefix != "ripper.progress" or not scope:
        return False
    job = (await session.execute(select(Job).where(col(Job.id) == scope))).scalar_one_or_none()
    if job is None:
        return False
    drive = (await session.execute(select(Drive).where(col(Drive.id) == job.drive_id))).scalar_one_or_none()
    return drive is not None and drive.hostname == principal.hostname


async def _transcoder_may_publish(
    principal: ServicePrincipal, prefix: str, scope: str | None, session: AsyncSession
) -> bool:
    """A transcoder may publish progress only for the in-progress task it
    claimed.
    """
    if prefix != "transcode.progress" or not scope or scope != principal.task_id:
        return False
    task = (await session.execute(select(TranscodeTask).where(col(TranscodeTask.id) == scope))).scalar_one_or_none()
    return task is not None and task.claimed_by == principal.hostname and task.status == TranscodeTaskStatus.IN_PROGRESS


_PUBLISH_RULES: dict[PrincipalKind, _ServiceRule] = {
    "ripper": _ripper_may_publish,
    "transcoder": _transcoder_may_publish,
}


async def can_subscribe(principal: Principal, topic: str, session: AsyncSession) -> bool:
    prefix, scope = _split(topic)

    if isinstance(principal, ServicePrincipal):
        return await _SUBSCRIBE_RULES[principal.kind](principal, prefix, scope, session)
    return _ui_may_subscribe(topic, prefix, scope)


async def can_publish(principal: Principal, topic: str, session: AsyncSession) -> bool:
    prefix, scope = _split(topic)

    if isinstance(principal, ServicePrincipal):
        return await _PUBLISH_RULES[principal.kind](principal, prefix, scope, session)

    # UI never publishes; backend uses hub.emit() in-process.
    return False
