"""Run a job-log milestone so that a failure in it never undoes the work that reached the milestone.

A Python-level failure in the logging is logged and swallowed. A database error inside an async
`work` is not undone: it can leave the session needing a rollback, so callers run milestone logs
after their commit where they can.
"""

import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


async def log_safely(event: str, work: Awaitable[None]) -> None:
    """Await a milestone log; a failure in it is logged, never raised into the caller."""
    try:
        await work
    except Exception:
        logger.exception("could not log the %s milestone", event)


def log_safely_sync[**P](event: str, work: Callable[P, None], /, *args: P.args, **kwargs: P.kwargs) -> None:
    """Call a milestone log with the given arguments; a failure in it is logged, never raised into the caller."""
    try:
        work(*args, **kwargs)
    except Exception:
        logger.exception("could not log the %s milestone", event)
