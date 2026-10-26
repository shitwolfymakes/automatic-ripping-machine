"""A docker-py client that reopens a dead docker-over-SSH transport.

An idle paramiko transport that the remote end has reset fails every later
call ("SSH session not active") until something builds a new client. Every
user of the transcode docker host (the probe, the spawn, the GPU probe runner)
goes through one `HealingDockerClient`, so whichever call meets the dead
transport first rebuilds it, once, for all of them.

Only method calls made through the wrapper heal (`client.ping()`,
`client.containers.run(...)`). Objects docker-py hands back, such as a
`Container`, stay bound to the client that made them; their calls are not
retried.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any, NoReturn

from paramiko.ssh_exception import SSHException  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# A dead docker-over-SSH transport (idle paramiko connection reset by the
# remote end) surfaces as one of these, either raw or wrapped inside
# docker-py's APIError cause chain. EOFError is included because paramiko
# commonly surfaces a dead transport that way (the read side hits EOF when
# the remote end has silently closed the connection).
_TRANSPORT_DEAD_ERRORS = (SSHException, ConnectionResetError, BrokenPipeError, EOFError)

# After a failed rebuild, calls that meet the dead transport fail with that
# rebuild's error for this long instead of starting another SSH handshake
# each (a black-holed host stalls every handshake for docker-py's timeout).
# Matches docker_probe.PROBE_TTL_SECONDS, so each probe window costs one.
REBUILD_RETRY_SECONDS = 30.0

# A replaced client is closed this long after its replacement goes in, not at
# once: a caller may still hold a `Container` it returned (a GPU probe waits
# on one for up to gpu_probe_runner.PROBE_TIMEOUT_S), and a transport judged
# dead by one error is not always dead for every channel. 0 closes at once.
RETIRED_CLIENT_CLOSE_DELAY_SECONDS = 300.0


def is_transport_death(exc: BaseException) -> bool:
    """A dead docker-over-SSH transport surfaces either as a raw paramiko
    SSHException or wrapped inside docker's APIError cause chain (docker-py
    wraps the underlying requests/urllib3 error, whose root cause is
    paramiko's SSHException). Walk __cause__/__context__ to find it.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, _TRANSPORT_DEAD_ERRORS):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


class DockerClientRebuildError(Exception):
    """The transport was dead and no replacement client could be built. The
    message names both the transport error and why the rebuild failed."""


def _close_quietly(client: Any) -> None:
    try:
        client.close()
    except Exception:  # noqa: BLE001 - best-effort cleanup of a replaced client
        pass


class HealingDockerClient:
    """Forwards method calls to the current docker client. A call that fails
    on a dead transport rebuilds the client through `factory` and is retried
    once on the new one; a second failure propagates.

    Rebuilds are serialised: threads that met the same dead client wait for
    the first one's rebuild and retry on its result instead of building (and
    closing) their own. A factory that raises or returns None keeps the old
    client, so a later call tries again after REBUILD_RETRY_SECONDS.
    """

    def __init__(
        self,
        client: Any,
        factory: Callable[[], Any] | None,
        *,
        on_rebuild: Callable[[], None] | None = None,
    ) -> None:
        self._client = client
        self._factory = factory
        self._on_rebuild = on_rebuild
        self._lock = threading.Lock()
        # (monotonic time, why) of the last failed rebuild of `_client`.
        self._rebuild_failed: tuple[float, str] | None = None

    @property
    def current(self) -> Any:
        """The docker-py client calls go to right now."""
        return self._client

    def __getattr__(self, name: str) -> _Method:
        return _Method(self, (name,))

    def call(self, path: tuple[str, ...], *args: Any, **kwargs: Any) -> Any:
        client = self._client
        try:
            return _resolve(client, path)(*args, **kwargs)
        except Exception as exc:
            fresh = self._replacement_for(client, exc, ".".join(path))
            if fresh is None:
                raise
        return _resolve(fresh, path)(*args, **kwargs)

    def _replacement_for(self, failed: Any, exc: Exception, what: str) -> Any | None:
        """The client to retry on after `failed` raised `exc`, or None to let
        `exc` stand. Raises DockerClientRebuildError when the transport is
        dead and no replacement could be built."""
        if self._factory is None or not is_transport_death(exc):
            return None
        with self._lock:
            if self._client is not failed:
                # Another thread already replaced the client this call used.
                return self._client
            if self._rebuild_failed is not None:
                failed_at, why = self._rebuild_failed
                if time.monotonic() - failed_at < REBUILD_RETRY_SECONDS:
                    raise DockerClientRebuildError(f"{exc} ({why})") from exc
            logger.warning("docker ssh transport dead; rebuilding client and retrying %s: %s", what, exc)
            try:
                rebuilt = self._factory()
            except Exception as factory_exc:  # noqa: BLE001 - reported through the call that needed it
                self._fail_rebuild(exc, f"rebuilding the docker client failed: {factory_exc}", factory_exc)
            if rebuilt is None:
                self._fail_rebuild(exc, "rebuilding the docker client returned no client", exc)
            self._client = rebuilt
            self._rebuild_failed = None
            self._retire(failed)
            if self._on_rebuild is not None:
                self._on_rebuild()
            return rebuilt

    def _fail_rebuild(self, exc: Exception, why: str, cause: BaseException) -> NoReturn:
        logger.warning("%s; keeping the old client", why)
        self._rebuild_failed = (time.monotonic(), why)
        raise DockerClientRebuildError(f"{exc} ({why})") from cause

    def _retire(self, old: Any) -> None:
        delay = RETIRED_CLIENT_CLOSE_DELAY_SECONDS
        if delay <= 0:
            _close_quietly(old)
            return
        timer = threading.Timer(delay, _close_quietly, args=(old,))
        timer.daemon = True
        timer.start()


class _Method:
    """An attribute path on a HealingDockerClient (`containers.run`), called
    through it."""

    __slots__ = ("_owner", "_path")

    def __init__(self, owner: HealingDockerClient, path: tuple[str, ...]) -> None:
        self._owner = owner
        self._path = path

    def __getattr__(self, name: str) -> _Method:
        return _Method(self._owner, (*self._path, name))

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._owner.call(self._path, *args, **kwargs)


def _resolve(client: Any, path: tuple[str, ...]) -> Callable[..., Any]:
    target = client
    for name in path:
        target = getattr(target, name)
    return target  # type: ignore[no-any-return]
