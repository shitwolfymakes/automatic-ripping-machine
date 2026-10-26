"""Tests for `HealingDockerClient`: forwarding, the dead-transport rebuild and
its retry, rebuild serialisation, the failed-rebuild backoff, and deferred
close of a replaced client."""

from __future__ import annotations

import threading
from typing import Any
from unittest.mock import MagicMock

import docker.errors  # type: ignore[import-untyped]
import pytest
from paramiko.ssh_exception import SSHException

from arm_backend import docker_client as docker_client_mod
from arm_backend.docker_client import (
    REBUILD_RETRY_SECONDS,
    DockerClientRebuildError,
    HealingDockerClient,
    is_transport_death,
)
from arm_backend.docker_probe import probe_docker


def _dead() -> SSHException:
    return SSHException("SSH session not active")


# ---- is_transport_death -----------------------------------------------------


def test_is_transport_death_detects_direct_eof_error() -> None:
    """Fix 76-9: paramiko commonly surfaces a dead transport as a raw
    EOFError (not just SSHException/ConnectionResetError/BrokenPipeError)."""
    assert is_transport_death(EOFError("EOF"))


def test_is_transport_death_detects_eof_error_nested_in_cause_chain() -> None:
    """docker-py wraps the underlying transport error; walk __cause__ to
    find an EOFError root cause, same as the existing SSHException path."""
    inner = EOFError("EOF")
    try:
        try:
            raise inner
        except EOFError as e:
            raise RuntimeError("docker APIError wrapper") from e
    except RuntimeError as wrapped:
        assert is_transport_death(wrapped)


def test_is_transport_death_rejects_unrelated_error() -> None:
    assert not is_transport_death(ValueError("not a transport error"))


# ---- forwarding and the rebuild ---------------------------------------------


def test_forwards_nested_method_calls() -> None:
    raw = MagicMock()
    raw.containers.run.return_value = "container"
    client = HealingDockerClient(raw, None)

    assert client.containers.run(image="img", detach=True) == "container"
    raw.containers.run.assert_called_once_with(image="img", detach=True)
    assert client.current is raw


def test_non_transport_error_propagates_without_a_rebuild() -> None:
    raw = MagicMock()
    raw.ping.side_effect = docker.errors.DockerException("connect refused")
    factory = MagicMock()
    client = HealingDockerClient(raw, factory)

    with pytest.raises(docker.errors.DockerException, match="connect refused"):
        client.ping()
    factory.assert_not_called()


def test_without_factory_a_dead_transport_propagates() -> None:
    raw = MagicMock()
    raw.ping.side_effect = _dead()
    client = HealingDockerClient(raw, None)

    with pytest.raises(SSHException):
        client.ping()
    assert client.current is raw


def test_dead_transport_rebuilds_and_retries_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_client_mod, "RETIRED_CLIENT_CLOSE_DELAY_SECONDS", 0.0)
    dead = MagicMock()
    dead.images.get.side_effect = _dead()
    fresh = MagicMock()
    fresh.images.get.return_value = "image"
    rebuilt: list[int] = []
    client = HealingDockerClient(dead, lambda: fresh, on_rebuild=lambda: rebuilt.append(1))

    assert client.images.get("img") == "image"
    assert client.current is fresh
    assert rebuilt == [1]
    dead.close.assert_called_once()


def test_second_failure_on_the_rebuilt_client_propagates() -> None:
    dead = MagicMock()
    dead.ping.side_effect = _dead()
    still_dead = MagicMock()
    still_dead.ping.side_effect = SSHException("still not active")
    factory = MagicMock(return_value=still_dead)
    client = HealingDockerClient(dead, factory)

    with pytest.raises(SSHException, match="still not active"):
        client.ping()
    factory.assert_called_once()


def test_probe_docker_heals_a_transport_that_dies_after_the_ping() -> None:
    """The ping answers, then the transport dies before the image check; the
    image check rebuilds instead of caching a failure against the dead
    client."""
    dead = MagicMock()
    dead.images.get.side_effect = docker.errors.APIError("boom")
    dead.images.get.side_effect.__cause__ = _dead()
    fresh = MagicMock()
    client = HealingDockerClient(dead, lambda: fresh)

    assert probe_docker(client, "img:test") == (True, None)
    fresh.images.get.assert_called_once_with("img:test")


# ---- serialised rebuilds ------------------------------------------------------


def test_concurrent_callers_share_one_rebuild_and_keep_its_client() -> None:
    """Two threads meet the same dead client. The first rebuilds; the second
    must retry on that client, not build (and close it for) another one."""
    both_failed = threading.Barrier(2, timeout=5)

    def dead_ping() -> None:
        both_failed.wait()
        raise _dead()

    dead = MagicMock()
    dead.ping.side_effect = dead_ping
    fresh = MagicMock()
    fresh.ping.return_value = True
    builds: list[int] = []

    def factory() -> MagicMock:
        builds.append(1)
        return fresh

    client = HealingDockerClient(dead, factory)
    results: list[Any] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            results.append(client.ping())
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assert below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert errors == []
    assert results == [True, True]
    assert builds == [1]
    assert client.current is fresh
    fresh.close.assert_not_called()


# ---- failed rebuilds ----------------------------------------------------------


def test_failed_rebuild_names_both_errors_and_backs_off(monkeypatch: pytest.MonkeyPatch) -> None:
    now = {"t": 1000.0}
    monkeypatch.setattr(docker_client_mod.time, "monotonic", lambda: now["t"])
    dead = MagicMock()
    dead.ping.side_effect = _dead()
    fresh = MagicMock()
    builds: list[int] = []

    def factory() -> MagicMock:
        builds.append(1)
        if len(builds) == 1:
            raise SSHException("Bad host key")
        return fresh

    client = HealingDockerClient(dead, factory)

    with pytest.raises(DockerClientRebuildError) as first:
        client.ping()
    assert "SSH session not active" in str(first.value)
    assert "Bad host key" in str(first.value)
    assert isinstance(first.value.__cause__, SSHException)
    assert client.current is dead

    # Inside the window: the remembered reason, no new handshake.
    with pytest.raises(DockerClientRebuildError, match="Bad host key"):
        client.ping()
    assert builds == [1]

    now["t"] += REBUILD_RETRY_SECONDS + 1.0
    client.ping()
    assert builds == [1, 1]
    assert client.current is fresh


def test_factory_returning_none_keeps_the_old_client() -> None:
    dead = MagicMock()
    dead.ping.side_effect = _dead()
    client = HealingDockerClient(dead, lambda: None)

    with pytest.raises(DockerClientRebuildError, match="returned no client"):
        client.ping()
    assert client.current is dead


# ---- retiring the replaced client ----------------------------------------------


def test_replaced_client_is_closed_after_the_delay_not_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """A GPU probe may still be waiting on a container the old client
    returned; closing it at once would fail that wait."""
    timers: list[tuple[float, Any, tuple[Any, ...]]] = []

    class _Timer:
        def __init__(self, delay: float, fn: Any, args: tuple[Any, ...]) -> None:
            timers.append((delay, fn, args))
            self.daemon = False

        def start(self) -> None:
            pass

    monkeypatch.setattr(docker_client_mod.threading, "Timer", _Timer)
    dead = MagicMock()
    dead.ping.side_effect = _dead()
    client = HealingDockerClient(dead, MagicMock())

    client.ping()

    dead.close.assert_not_called()
    [(delay, fn, args)] = timers
    assert delay == docker_client_mod.RETIRED_CLIENT_CLOSE_DELAY_SECONDS
    fn(*args)
    dead.close.assert_called_once()


def test_close_failure_of_a_replaced_client_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_client_mod, "RETIRED_CLIENT_CLOSE_DELAY_SECONDS", 0.0)
    dead = MagicMock()
    dead.ping.side_effect = _dead()
    dead.close.side_effect = OSError("already closed")
    fresh = MagicMock()
    client = HealingDockerClient(dead, lambda: fresh)

    client.ping()

    assert client.current is fresh
