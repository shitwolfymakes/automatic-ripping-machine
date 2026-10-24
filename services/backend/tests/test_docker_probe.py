from __future__ import annotations

from unittest.mock import MagicMock

import docker.errors

from arm_backend.docker_probe import PROBE_TTL_SECONDS, TtlProbe, probe_docker


def test_probe_docker_ok() -> None:
    client = MagicMock()
    assert probe_docker(client, "img:test") == (True, None)
    client.images.get.assert_called_once_with("img:test")


def test_probe_docker_unreachable_wins_over_image() -> None:
    client = MagicMock()
    client.ping.side_effect = docker.errors.DockerException("connect refused")
    client.images.get.side_effect = docker.errors.ImageNotFound("nope")
    ok, detail = probe_docker(client, "img:test")
    assert ok is False and detail == "docker host unreachable: connect refused"
    client.images.get.assert_not_called()


def test_probe_docker_missing_image() -> None:
    client = MagicMock()
    client.images.get.side_effect = docker.errors.ImageNotFound("nope")
    assert probe_docker(client, "img:test") == (False, "image img:test not present on docker host")


def test_probe_docker_image_check_failure() -> None:
    client = MagicMock()
    client.images.get.side_effect = docker.errors.APIError("boom")
    ok, detail = probe_docker(client, "img:test")
    assert ok is False and detail is not None and detail.startswith("image check failed: ")


def test_ttl_probe_caches_failures_within_ttl(monkeypatch) -> None:
    now = {"t": 1000.0}
    monkeypatch.setattr("arm_backend.docker_probe.time.monotonic", lambda: now["t"])
    calls = {"n": 0}

    def fn() -> tuple[bool, str | None]:
        calls["n"] += 1
        return (False, "down")

    probe = TtlProbe(fn)
    assert probe() == (False, "down")
    assert probe() == (False, "down")
    assert calls["n"] == 1
    now["t"] += PROBE_TTL_SECONDS + 1.0
    assert probe() == (False, "down")
    assert calls["n"] == 2


def test_probe_docker_recover_swaps_in_a_fresh_client() -> None:
    # A dead transport on ping hands the exception to `recover`; the client
    # it returns answers the rest of the probe.
    dead = MagicMock()
    exc = docker.errors.DockerException("SSH session not active")
    dead.ping.side_effect = exc
    fresh = MagicMock()
    seen: list[BaseException] = []

    def recover(e: BaseException) -> MagicMock:
        seen.append(e)
        return fresh

    assert probe_docker(dead, "img:test", recover=recover) == (True, None)
    assert seen == [exc]
    fresh.ping.assert_called_once()
    fresh.images.get.assert_called_once_with("img:test")
    dead.images.get.assert_not_called()


def test_probe_docker_recover_declining_reports_the_original_error() -> None:
    dead = MagicMock()
    dead.ping.side_effect = docker.errors.DockerException("connect refused")
    ok, detail = probe_docker(dead, "img:test", recover=lambda _e: None)
    assert ok is False and detail == "docker host unreachable: connect refused"
    dead.images.get.assert_not_called()


def test_probe_docker_recovered_client_still_dead_reports_its_error() -> None:
    dead = MagicMock()
    dead.ping.side_effect = docker.errors.DockerException("SSH session not active")
    still_dead = MagicMock()
    still_dead.ping.side_effect = docker.errors.DockerException("connect timed out")
    calls: list[int] = []

    def recover(_e: BaseException) -> MagicMock:
        calls.append(1)
        return still_dead

    ok, detail = probe_docker(dead, "img:test", recover=recover)
    assert ok is False and detail == "docker host unreachable: connect timed out"
    assert calls == [1]  # one recovery attempt, no loop
    still_dead.images.get.assert_not_called()
